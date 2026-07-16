#!/bin/bash
################################################################################
# OpenStack CLI Commands for Physical Network Fallback Removal
# Session: 2026-07-16_Remove_Physical_Network_Fallback
#
# Purpose: Commands for auditing, validating, and testing the removal of
#          physical_network fallback lookup from Neutron mechanism driver
#
# Usage:
#   ./openstack_cli_commands.sh [command] [options]
#   ./openstack_cli_commands.sh audit [environment]
#   ./openstack_cli_commands.sh validate-port <port-id>
#   ./openstack_cli_commands.sh list-missing [environment]
#
################################################################################

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="${ENVIRONMENT:-}"
VERBOSE=false

# Parse global flags before command
while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        *)
            break
            ;;
    esac
done

################################################################################
# Helper Functions
################################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Log verbose command execution
log_command() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${YELLOW}[EXEC]${NC} $*"
    fi
}

print_usage() {
    cat <<EOF
Usage: $0 [OPTIONS] [COMMAND] [COMMAND_OPTIONS]

GLOBAL OPTIONS:
  -v, --verbose                - Show OpenStack CLI commands being executed
  -h, --help                   - Show this help message

COMMANDS:
  audit [env]                  - Audit all ports in environment for physical_network
  validate-port <port-id>      - Check if a specific port has physical_network
  list-missing [env]           - List all ports missing physical_network
  count-ports [env]            - Count total ports and those missing physical_network
  show-port <port-id>          - Display port binding profile details
  update-port <port-id> <vlan> - Update port with physical_network
  test-port-creation           - Test creating port with physical_network
  test-trunk-ops               - Test trunk operations with physical_network
  batch-update <vlan> [env]    - Batch update all ports in environment
  diagnose                     - Run OpenStack environment diagnostics
  help                         - Show this help message

GLOBAL OPTIONS (legacy):
  -e, --environment ENV        - Set OpenStack environment (uc-iad3-dev, uc-iad3-staging, uc-dfw3-prod)
  -f, --format FORMAT          - Output format (json, table, yaml) - default: json

ENVIRONMENTS:
  - uc-iad3-dev
  - uc-iad3-staging
  - uc-dfw3-prod

EXAMPLES:
  # Audit development environment
  $0 audit uc-iad3-dev

  # List ports missing physical_network with verbose output
  $0 -v list-missing uc-iad3-staging

  # Validate a specific port with command details
  $0 --verbose validate-port <port-uuid>

  # Count ports in production
  $0 count-ports uc-dfw3-prod

  # Update a port with physical_network
  $0 update-port <port-uuid> vlan_group_1

  # Batch update all ports in staging with verbose output
  $0 -v batch-update vlan_group_1 uc-iad3-staging

VERBOSE MODE:
  Use -v or --verbose flag to see the actual OpenStack CLI commands being executed.

  Example:
    $0 -v audit uc-iad3-dev

  Output will show:
    [EXEC] openstack port list --format json
    [INFO] Counting ports in environment: uc-iad3-dev
    ...

EOF
}

################################################################################
# Port Information Commands
################################################################################

# Show port binding profile in detail
show_port_binding_profile() {
    local port_id="$1"

    if [[ -z "$port_id" ]]; then
        log_error "Port ID required"
        return 1
    fi

    log_info "Retrieving binding profile for port: $port_id"
    log_command "openstack port show $port_id -f json"

    openstack port show "$port_id" -f json | python3 -m json.tool | \
        grep -A 50 "binding_profile" || {
        log_error "Could not find binding_profile for port $port_id"
        return 1
    }
}

# Validate single port has physical_network
validate_port() {
    local port_id="$1"

    if [[ -z "$port_id" ]]; then
        log_error "Port ID required"
        return 1
    fi

    log_info "Validating port: $port_id"
    log_command "openstack port show $port_id -f json"

    local binding_profile
    binding_profile=$(openstack port show "$port_id" -f json | \
        python3 -c "import sys, json; data=json.load(sys.stdin); \
        print(json.dumps(data.get('binding_profile', {})))" 2>/dev/null || echo "{}")

    if [[ -z "$binding_profile" || "$binding_profile" == "{}" ]]; then
        log_warning "Port $port_id has no binding_profile"
        return 1
    fi

    local has_physical_network
    has_physical_network=$(echo "$binding_profile" | \
        python3 -c "import sys, json; data=json.loads(sys.stdin.read()); \
        print('yes' if 'physical_network' in data else 'no')" 2>/dev/null || echo "no")

    if [[ "$has_physical_network" == "yes" ]]; then
        log_success "Port $port_id HAS physical_network"
        echo "$binding_profile" | python3 -m json.tool
        return 0
    else
        log_warning "Port $port_id MISSING physical_network"
        echo "$binding_profile" | python3 -m json.tool
        return 1
    fi
}

################################################################################
# Audit Commands
################################################################################

# List all ports missing physical_network
list_ports_missing_physical_network() {
    local env="${1:-}"

    log_info "Listing ports missing physical_network in environment: ${env:-current}"

    if [[ -n "$env" ]]; then
        log_info "Note: Ensure you are authenticated to $env before running this command"
    fi

    local tmpfile
    tmpfile=$(mktemp -t openstack-ports.XXXXXX)

    log_command "openstack port list --format json"
    openstack port list --format json 2>/dev/null > "$tmpfile"

    if [[ ! -s "$tmpfile" ]]; then
        log_error "No port data returned from OpenStack. Check authentication."
        rm -f "$tmpfile"
        return 1
    fi

    python3 - "$tmpfile" << 'PYTHON_SCRIPT_END'
import sys
import json
import os

tmpfile = sys.argv[1]

try:
    if not os.path.exists(tmpfile):
        print(f"Error: Temp file not found: {tmpfile}", file=sys.stderr)
        sys.exit(1)

    with open(tmpfile, 'r') as f:
        data = json.load(f)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON from OpenStack: {e}", file=sys.stderr)
    sys.exit(1)
except FileNotFoundError as e:
    print(f"Error: Temp file not found: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    # Clean up temp file
    try:
        if os.path.exists(tmpfile):
            os.remove(tmpfile)
    except:
        pass

# Handle both array and object formats
if isinstance(data, list):
    ports = data
else:
    ports = data.get('ports', [])

missing_ports = []

for port in ports:
    binding_profile = port.get('binding_profile', '{}')

    # Parse binding_profile if it's a string
    if isinstance(binding_profile, str):
        try:
            binding_profile = json.loads(binding_profile) if binding_profile else {}
        except json.JSONDecodeError:
            binding_profile = {}

    # Check if port has local_link_information but no physical_network
    if 'local_link_information' in str(binding_profile) and \
       'physical_network' not in str(binding_profile):
        missing_ports.append({
            'id': port.get('ID', port.get('id', 'N/A')),
            'name': port.get('Name', port.get('name', 'N/A')),
            'device_id': port.get('device_id', 'N/A'),
            'binding_profile': binding_profile
        })

print(f"\n{'='*80}")
print(f"Total ports missing physical_network: {len(missing_ports)}")
print(f"{'='*80}\n")

if missing_ports:
    for idx, port in enumerate(missing_ports[:20], 1):
        print(f"[{idx}] Port ID: {port['id']}")
        print(f"    Name: {port['name']}")
        print(f"    Device: {port['device_id']}")
        print(f"    Binding Profile: {json.dumps(port['binding_profile'], indent=6)}")
        print()

    if len(missing_ports) > 20:
        print(f"... and {len(missing_ports) - 20} more ports\n")
else:
    print("All ports have physical_network defined!\n")

sys.exit(0 if len(missing_ports) == 0 else 1)
PYTHON_SCRIPT_END
}

# Count ports and report missing physical_network
count_ports_status() {
    local env="${1:-}"

    log_info "Counting ports in environment: ${env:-current}"

    local tmpfile
    tmpfile=$(mktemp -t openstack-ports.XXXXXX)

    log_command "openstack port list --format json"
    openstack port list --format json 2>/dev/null > "$tmpfile"

    if [[ ! -s "$tmpfile" ]]; then
        log_error "No port data returned from OpenStack. Check authentication with: openstack token issue"
        rm -f "$tmpfile"
        return 1
    fi

    python3 - "$tmpfile" << 'PYTHON_SCRIPT_END'
import sys
import json
import os

tmpfile = sys.argv[1]

try:
    if not os.path.exists(tmpfile):
        print(f"Error: Temp file not found: {tmpfile}", file=sys.stderr)
        sys.exit(1)

    with open(tmpfile, 'r') as f:
        data = json.load(f)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON from OpenStack: {e}", file=sys.stderr)
    sys.exit(1)
except FileNotFoundError as e:
    print(f"Error: Temp file not found: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    # Clean up temp file
    try:
        if os.path.exists(tmpfile):
            os.remove(tmpfile)
    except:
        pass

# Handle both array and object formats
if isinstance(data, list):
    ports = data
else:
    ports = data.get('ports', [])

total_ports = len(ports)
baremetal_ports = 0
missing_physical_network = 0

for port in ports:
    binding_profile = port.get('binding_profile', '{}')

    # Parse binding_profile if it's a string
    if isinstance(binding_profile, str):
        try:
            binding_profile = json.loads(binding_profile) if binding_profile else {}
        except json.JSONDecodeError:
            binding_profile = {}

    # Check if baremetal (has local_link_information)
    if 'local_link_information' in str(binding_profile):
        baremetal_ports += 1

        # Check for physical_network
        if 'physical_network' not in str(binding_profile):
            missing_physical_network += 1

print(f"\n{'='*60}")
print(f"Port Statistics")
print(f"{'='*60}")
print(f"Total Ports:                        {total_ports}")
print(f"Baremetal Ports (with local_link): {baremetal_ports}")
print(f"Missing physical_network:          {missing_physical_network}")
print(f"Compliant Baremetal Ports:         {baremetal_ports - missing_physical_network}")
print(f"{'='*60}\n")

if baremetal_ports > 0:
    compliance = ((baremetal_ports - missing_physical_network) / baremetal_ports) * 100
    print(f"Compliance Rate: {compliance:.1f}%\n")
PYTHON_SCRIPT_END
}

# Full audit report
audit_environment() {
    local env="$1"

    log_info "Running full audit for environment: ${env:-current}"
    echo ""

    # Summary
    count_ports_status "$env"

    echo ""
    log_info "Listing missing ports (first 10)..."
    list_ports_missing_physical_network "$env" || true
}

################################################################################
# Update Commands
################################################################################

# Update single port with physical_network
update_port_with_physical_network() {
    local port_id="$1"
    local physical_network="$2"

    if [[ -z "$port_id" ]]; then
        log_error "Port ID required"
        return 1
    fi

    if [[ -z "$physical_network" ]]; then
        log_error "Physical network name required"
        return 1
    fi

    log_info "Updating port $port_id with physical_network: $physical_network"
    log_command "openstack port show $port_id -f json"

    # Get current binding profile
    local current_profile
    current_profile=$(openstack port show "$port_id" -f json | \
        python3 -c "import sys, json; data=json.load(sys.stdin); \
        print(json.dumps(data.get('binding_profile', {})))" 2>/dev/null || echo "{}")

    log_info "Current binding profile: $current_profile"

    # Update port with physical_network
    log_command "openstack port set $port_id --binding-profile physical_network=$physical_network"
    if openstack port set "$port_id" \
        --binding-profile "physical_network=$physical_network"; then
        log_success "Port $port_id updated successfully"

        # Verify update
        sleep 1
        validate_port "$port_id"
        return 0
    else
        log_error "Failed to update port $port_id"
        return 1
    fi
}

# Batch update all baremetal ports in environment
batch_update_ports() {
    local physical_network="$1"
    local env="$2"

    if [[ -z "$physical_network" ]]; then
        log_error "Physical network name required"
        return 1
    fi

    log_warning "This will update ALL baremetal ports missing physical_network"
    read -p "Continue? (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cancelled"
        return 0
    fi

    log_info "Batch updating ports with physical_network: $physical_network"

    local updated_count=0
    local failed_count=0

    # Get list of missing ports
    local tmpfile
    tmpfile=$(mktemp)
    trap 'rm -f "$tmpfile"' RETURN

    openstack port list --format json 2>/dev/null | python3 << 'PYTHON_SCRIPT' > "$tmpfile"
import sys
import json

data = json.load(sys.stdin)

# Handle both array and object formats
if isinstance(data, list):
    ports = data
else:
    ports = data.get('ports', [])

for port in ports:
    binding_profile = port.get('binding_profile', '{}')

    if isinstance(binding_profile, str):
        try:
            binding_profile = json.loads(binding_profile) if binding_profile else {}
        except json.JSONDecodeError:
            binding_profile = {}

    if 'local_link_information' in str(binding_profile) and \
       'physical_network' not in str(binding_profile):
        print(port.get('ID', port.get('id', '')))
PYTHON_SCRIPT

    while read -r port_id; do
        if [[ -n "$port_id" ]]; then
            log_info "Updating port: $port_id"
            if openstack port set "$port_id" \
                --binding-profile "physical_network=$physical_network"; then
                ((updated_count++))
                log_success "Updated port $port_id"
            else
                ((failed_count++))
                log_error "Failed to update port $port_id"
            fi
            sleep 1
        fi
    done < "$tmpfile"

    echo ""
    log_success "Batch update complete!"
    echo "Updated: $updated_count"
    echo "Failed: $failed_count"
}

################################################################################
# Test Commands
################################################################################

# Test port creation with physical_network
test_port_creation() {
    local network_id="${1:-}"

    # If a parameter is provided, check if it looks like a UUID (network ID)
    # If not, it might be an environment name - just proceed without it
    if [[ -n "$network_id" ]]; then
        # Check if it looks like a UUID (too short = not a UUID)
        if [[ ${#network_id} -lt 32 ]]; then
            log_info "Parameter '$network_id' doesn't look like a network UUID, finding network automatically..."
            network_id=""
        fi
    fi

    # If no valid network ID, find one
    if [[ -z "$network_id" ]]; then
        log_warning "Network ID not provided, attempting to find default network..."
        log_command "openstack network list -f value -c ID"
        network_id=$(openstack network list -f value -c ID 2>/dev/null | head -1)

        if [[ -z "$network_id" ]]; then
            log_error "Could not find network. Please provide network ID as argument"
            return 1
        fi
    fi

    log_info "Testing port creation with physical_network"
    log_info "Network ID: $network_id"

    local test_port_name
    test_port_name="test-physical-network-$(date +%s)"

    log_info "Creating test port: $test_port_name"
    log_command "openstack port create --network $network_id --format value -c id $test_port_name"

    local port_id
    port_id=$(openstack port create \
        --network "$network_id" \
        --format value -c id \
        "$test_port_name" 2>/dev/null || echo "")

    if [[ -z "$port_id" ]]; then
        log_error "Failed to create test port"
        log_error "Make sure you have a valid network. Check with: openstack network list"
        return 1
    fi

    log_success "Test port created: $port_id"

    # Add binding profile with physical_network
    log_info "Adding binding profile with physical_network..."
    log_command "openstack port set $port_id --binding-profile '{...}'"
    if openstack port set "$port_id" \
        --binding-profile '{"local_link_information":{"switch_id":"test-switch","port_id":"port-1"},"physical_network":"test_vlan_group"}'; then
        log_success "Binding profile set successfully"
    else
        log_error "Failed to set binding profile"
        log_warning "This may be a policy restriction. Check with your OpenStack admin."
        log_warning "Your account may not have permission to set binding profiles."
        log_info "Cleaning up test port $port_id..."
        openstack port delete "$port_id"
        return 1
    fi

    # Verify
    log_info "Verifying port binding profile..."
    if validate_port "$port_id"; then
        log_success "Test port creation and validation PASSED"
        log_info "Cleaning up test port..."
        openstack port delete "$port_id"
        return 0
    else
        log_error "Test port validation FAILED"
        log_warning "Leaving test port $port_id for manual inspection"
        return 1
    fi
}

# Test trunk operations with physical_network
test_trunk_operations() {
    local network_id="${1:-}"

    # If a parameter is provided, check if it looks like a UUID (network ID)
    if [[ -n "$network_id" ]]; then
        # Check if it looks like a UUID (too short = not a UUID)
        if [[ ${#network_id} -lt 32 ]]; then
            log_info "Parameter '$network_id' doesn't look like a network UUID, finding network automatically..."
            network_id=""
        fi
    fi

    # If no valid network ID, find one
    if [[ -z "$network_id" ]]; then
        log_warning "Network ID not provided, attempting to find default network..."
        log_command "openstack network list -f value -c ID"
        network_id=$(openstack network list -f value -c ID 2>/dev/null | head -1)

        if [[ -z "$network_id" ]]; then
            log_error "Could not find network. Please provide network ID as argument"
            return 1
        fi
    fi

    log_info "Testing trunk operations with physical_network"

    local trunk_name
    trunk_name="test-trunk-$(date +%s)"
    local parent_port_name
    parent_port_name="test-parent-$(date +%s)"
    local subport_name
    subport_name="test-subport-$(date +%s)"

    # Create parent port
    log_info "Creating parent port: $parent_port_name"
    log_command "openstack port create --network $network_id --format value -c id $parent_port_name"
    local parent_port
    parent_port=$(openstack port create \
        --network "$network_id" \
        --format value -c id \
        "$parent_port_name" 2>/dev/null || echo "")

    if [[ -z "$parent_port" ]]; then
        log_error "Failed to create parent port"
        log_error "Make sure you have a valid network. Check with: openstack network list"
        return 1
    fi

    log_success "Parent port created: $parent_port"

    # Add binding profile to parent port
    log_info "Setting binding profile on parent port..."
    log_command "openstack port set $parent_port --binding-profile '{...}'"
    if ! openstack port set "$parent_port" \
        --binding-profile '{"local_link_information":{"switch_id":"test-switch","port_id":"port-parent"},"physical_network":"test_vlan_group"}'; then
        log_error "Failed to set binding profile on parent port"
        openstack port delete "$parent_port"
        return 1
    fi

    # Create subport
    log_info "Creating subport: $subport_name"
    log_command "openstack port create --network $network_id --format value -c id $subport_name"
    local subport
    subport=$(openstack port create \
        --network "$network_id" \
        --format value -c id \
        "$subport_name" 2>/dev/null || echo "")

    if [[ -z "$subport" ]]; then
        log_error "Failed to create subport"
        openstack port delete "$parent_port"
        return 1
    fi

    log_success "Subport created: $subport"

    # Create trunk
    log_info "Creating trunk: $trunk_name"
    log_command "openstack network trunk create --parent-port $parent_port $trunk_name"
    if openstack network trunk create \
        --parent-port "$parent_port" \
        "$trunk_name"; then
        log_success "Trunk created: $trunk_name"
    else
        log_error "Failed to create trunk"
        openstack port delete "$parent_port"
        openstack port delete "$subport"
        return 1
    fi

    # Add subport to trunk
    log_info "Adding subport to trunk..."
    log_command "openstack network trunk set --subport $subport $trunk_name"
    if openstack network trunk set --subport "$subport" "$trunk_name"; then
        log_success "Subport added to trunk successfully"
    else
        log_error "Failed to add subport to trunk"
        openstack network trunk delete "$trunk_name"
        openstack port delete "$parent_port"
        openstack port delete "$subport"
        return 1
    fi

    log_success "Trunk operations test PASSED"

    # Cleanup
    log_info "Cleaning up test resources..."
    openstack network trunk delete "$trunk_name" || true
    openstack port delete "$parent_port" || true
    openstack port delete "$subport" || true

    return 0
}

################################################################################
# Diagnostic Command
################################################################################

diagnose_environment() {
    echo ""
    log_info "OpenStack Environment Diagnostics"
    echo "=================================="
    echo ""

    # Check if openstack CLI is installed
    log_info "1. Checking OpenStack CLI installation..."
    if command -v openstack &> /dev/null; then
        log_success "OpenStack CLI is installed"
        openstack --version
    else
        log_error "OpenStack CLI not found. Install with: pip install python-openstackclient"
        return 1
    fi

    echo ""

    # Check authentication
    log_info "2. Checking OpenStack authentication..."
    if env | grep -q "OS_AUTH_URL"; then
        log_success "OpenStack environment variables are set:"
        env | grep "^OS_" | sed 's/^/   /'
    else
        log_warning "No OpenStack environment variables detected"
        log_info "Try: source /path/to/openrc.sh"
    fi

    echo ""

    # Try to get a token
    log_info "3. Attempting to retrieve authentication token..."
    if openstack token issue &> /dev/null; then
        log_success "Authentication successful!"
        openstack token issue
    else
        log_error "Authentication failed"
        log_warning "Verify your credentials and try again"
        return 1
    fi

    echo ""

    # Try to list ports
    log_info "4. Attempting to retrieve port list..."
    local port_count
    if port_count=$(openstack port list -c ID -f value 2>/dev/null | wc -l); then
        log_success "Port list retrieved successfully"
        log_info "Total ports: $port_count"
    else
        log_error "Failed to retrieve port list"
        return 1
    fi

    echo ""
    log_success "Diagnostics complete!"
    echo ""
}

################################################################################
# Main Script Logic
################################################################################

main() {
    local command="${1:-}"
    shift || true

    case "$command" in
        audit)
            audit_environment "$@"
            ;;
        validate-port)
            validate_port "$@"
            ;;
        list-missing)
            list_ports_missing_physical_network "$@"
            ;;
        count-ports)
            count_ports_status "$@"
            ;;
        show-port)
            show_port_binding_profile "$@"
            ;;
        update-port)
            update_port_with_physical_network "$@"
            ;;
        batch-update)
            batch_update_ports "$@"
            ;;
        test-port-creation)
            test_port_creation "$@"
            ;;
        test-trunk-ops)
            test_trunk_operations "$@"
            ;;
        diagnose|--diagnose|-d)
            diagnose_environment
            ;;
        help|--help|-h)
            print_usage
            ;;
        "")
            log_error "No command provided"
            echo ""
            print_usage
            exit 1
            ;;
        *)
            log_error "Unknown command: $command"
            echo ""
            print_usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
