#!/usr/bin/env bash
#
# cleanup-rally.sh — Find and clean up stale c_rally* project resources
#
# By default runs in dry-run mode. Pass --delete to actually remove resources.
#
set -euo pipefail

DELETE=false
VERBOSE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --delete        Actually delete resources (default is dry-run)
  --verbose       Show extra detail during execution
  -h, --help      Show this help
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --delete)  DELETE=true; shift ;;
        --verbose) VERBOSE=true; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

log()  { echo "[INFO]  $*"; }
warn() { echo "[WARN]  $*" >&2; }
dbg()  { if $VERBOSE; then echo "[DEBUG] $*"; fi; }

# ---------------------------------------------------------------------------
# Gather rally projects
# ---------------------------------------------------------------------------
log "Fetching project list..."
RALLY_PROJECTS=$(openstack project list -f json | \
    python3 -c "
import json, sys
data = json.load(sys.stdin)
for p in data:
    name = p.get('Name', '')
    if name.startswith('c_rally'):
        print(p['ID'] + ' ' + name)
")

if [[ -z "$RALLY_PROJECTS" ]]; then
    log "No c_rally* projects found. Nothing to do."
    exit 0
fi

PROJECT_COUNT=$(echo "$RALLY_PROJECTS" | wc -l | tr -d ' ')
log "Found $PROJECT_COUNT c_rally* project(s)"
if $DELETE; then
    warn "*** DELETE mode is active — resources WILL be removed ***"
else
    log "(dry-run mode — pass --delete to actually remove resources)"
fi
echo ""


# ---------------------------------------------------------------------------
# Per-resource-type cleanup helpers
# ---------------------------------------------------------------------------

delete_ports() {
    local project_id="$1"
    local project_name="$2"

    dbg "  Checking ports in $project_name..."
    local ports
    ports=$(openstack port list --project "$project_id" -f json 2>/dev/null || echo "[]")

    local port_lines
    port_lines=$(python3 -c "
import json, sys
data = json.load(sys.stdin)
for p in data:
    pid = p.get('ID', '')
    name = p.get('Name', '')
    device = p.get('Device Owner', '')
    print(pid + '|' + name + '|' + device)
" <<< "$ports")

    [[ -z "$port_lines" ]] && return

    while IFS='|' read -r port_id port_name device_owner; do
        [[ -z "$port_id" ]] && continue
        # Skip DHCP and router interface ports on first pass — they get cleaned
        # up when their parent is removed. We'll force-delete them if they linger.
        if [[ "$device_owner" == "network:dhcp" || "$device_owner" == "network:router_interface" ]]; then
            dbg "    Skipping port $port_id ($device_owner) — will be cleaned with parent"
            continue
        fi
        echo "    PORT: $port_id ($port_name) [device_owner=$device_owner]"
        if $DELETE; then
            if openstack port delete "$port_id"; then
                log "    Deleted port $port_id"
            else
                warn "    Failed to delete port $port_id"
            fi
        fi
    done <<< "$port_lines"
}

delete_floating_ips() {
    local project_id="$1"
    local project_name="$2"

    dbg "  Checking floating IPs in $project_name..."
    local fips
    fips=$(openstack floating ip list --project "$project_id" -f json 2>/dev/null || echo "[]")

    local fip_lines
    fip_lines=$(python3 -c "
import json, sys
for f in json.load(sys.stdin):
    print(f.get('ID','') + '|' + f.get('Floating IP Address',''))
" <<< "$fips")

    [[ -z "$fip_lines" ]] && return

    while IFS='|' read -r fip_id fip_addr; do
        [[ -z "$fip_id" ]] && continue
        echo "    FLOATING IP: $fip_id ($fip_addr)"
        if $DELETE; then
            if openstack floating ip delete "$fip_id"; then
                log "    Deleted floating IP $fip_id"
            else
                warn "    Failed to delete floating IP $fip_id"
            fi
        fi
    done <<< "$fip_lines"
}

delete_servers() {
    local project_id="$1"
    local project_name="$2"

    dbg "  Checking servers in $project_name..."
    local servers
    servers=$(openstack server list --project "$project_id" --all-projects -f json 2>/dev/null || echo "[]")

    local server_lines
    server_lines=$(python3 -c "
import json, sys
for s in json.load(sys.stdin):
    print(s.get('ID','') + '|' + s.get('Name','') + '|' + s.get('Status',''))
" <<< "$servers")

    [[ -z "$server_lines" ]] && return

    while IFS='|' read -r srv_id srv_name srv_status; do
        [[ -z "$srv_id" ]] && continue
        echo "    SERVER: $srv_id ($srv_name) [$srv_status]"
        if $DELETE; then
            if openstack server delete --wait "$srv_id"; then
                log "    Deleted server $srv_id"
            else
                warn "    Failed to delete server $srv_id"
            fi
        fi
    done <<< "$server_lines"
}

delete_images() {
    local project_id="$1"
    local project_name="$2"

    dbg "  Checking images in $project_name..."
    local images
    images=$(openstack image list --property owner="$project_id" -f json 2>/dev/null || echo "[]")

    local image_lines
    image_lines=$(python3 -c "
import json, sys
for i in json.load(sys.stdin):
    print(i.get('ID','') + '|' + i.get('Name','') + '|' + i.get('Status',''))
" <<< "$images")

    [[ -z "$image_lines" ]] && return

    while IFS='|' read -r img_id img_name img_status; do
        [[ -z "$img_id" ]] && continue
        echo "    IMAGE: $img_id ($img_name) [$img_status]"
        if $DELETE; then
            if openstack image delete "$img_id"; then
                log "    Deleted image $img_id"
            else
                warn "    Failed to delete image $img_id"
            fi
        fi
    done <<< "$image_lines"
}

delete_volumes() {
    local project_id="$1"
    local project_name="$2"

    dbg "  Checking volumes in $project_name..."
    local volumes
    volumes=$(openstack volume list --project "$project_id" --all-projects -f json 2>/dev/null || echo "[]")

    local vol_lines
    vol_lines=$(python3 -c "
import json, sys
for v in json.load(sys.stdin):
    print(v.get('ID','') + '|' + v.get('Name','') + '|' + v.get('Status',''))
" <<< "$volumes")

    [[ -z "$vol_lines" ]] && return

    while IFS='|' read -r vol_id vol_name vol_status; do
        [[ -z "$vol_id" ]] && continue
        echo "    VOLUME: $vol_id ($vol_name) [$vol_status]"
        if $DELETE; then
            if openstack volume delete "$vol_id"; then
                log "    Deleted volume $vol_id"
            else
                warn "    Failed to delete volume $vol_id"
            fi
        fi
    done <<< "$vol_lines"
}

delete_routers() {
    local project_id="$1"
    local project_name="$2"

    dbg "  Checking routers in $project_name..."
    local routers
    routers=$(openstack router list --project "$project_id" -f json 2>/dev/null || echo "[]")

    local router_lines
    router_lines=$(python3 -c "
import json, sys
for r in json.load(sys.stdin):
    print(r.get('ID','') + '|' + r.get('Name','') + '|' + r.get('Status',''))
" <<< "$routers")

    [[ -z "$router_lines" ]] && return

    while IFS='|' read -r rtr_id rtr_name rtr_status; do
        [[ -z "$rtr_id" ]] && continue
        echo "    ROUTER: $rtr_id ($rtr_name) [$rtr_status]"
        if $DELETE; then
            # Remove router interfaces (subnets) before deleting the router
            local rtr_ports
            rtr_ports=$(openstack port list --router "$rtr_id" -f json 2>/dev/null || echo "[]")
            local subnet_ids
            subnet_ids=$(python3 -c "
import json, sys
for p in json.load(sys.stdin):
    for ip in p.get('Fixed IP Addresses', []):
        sid = ip.get('subnet_id', '')
        if sid:
            print(sid)
" <<< "$rtr_ports")
            while read -r subnet_id; do
                [[ -z "$subnet_id" ]] && continue
                if openstack router remove subnet "$rtr_id" "$subnet_id" 2>/dev/null; then
                    log "    Removed subnet $subnet_id from router $rtr_id"
                fi
            done <<< "$subnet_ids"

            # Clear gateway if set
            openstack router unset --external-gateway "$rtr_id" 2>/dev/null || true

            if openstack router delete "$rtr_id"; then
                log "    Deleted router $rtr_id"
            else
                warn "    Failed to delete router $rtr_id"
            fi
        fi
    done <<< "$router_lines"
}

delete_subnets() {
    local project_id="$1"
    local project_name="$2"

    dbg "  Checking subnets in $project_name..."
    local subnets
    subnets=$(openstack subnet list --project "$project_id" -f json 2>/dev/null || echo "[]")

    local subnet_lines
    subnet_lines=$(python3 -c "
import json, sys
for s in json.load(sys.stdin):
    print(s.get('ID','') + '|' + s.get('Name','') + '|' + s.get('Subnet',''))
" <<< "$subnets")

    [[ -z "$subnet_lines" ]] && return

    while IFS='|' read -r sub_id sub_name sub_cidr; do
        [[ -z "$sub_id" ]] && continue
        echo "    SUBNET: $sub_id ($sub_name) [$sub_cidr]"
        if $DELETE; then
            if openstack subnet delete "$sub_id"; then
                log "    Deleted subnet $sub_id"
            else
                warn "    Failed to delete subnet $sub_id"
            fi
        fi
    done <<< "$subnet_lines"
}

delete_networks() {
    local project_id="$1"
    local project_name="$2"

    dbg "  Checking networks in $project_name..."
    local networks
    networks=$(openstack network list --project "$project_id" -f json 2>/dev/null || echo "[]")

    local net_lines
    net_lines=$(python3 -c "
import json, sys
for n in json.load(sys.stdin):
    print(n.get('ID','') + '|' + n.get('Name',''))
" <<< "$networks")

    [[ -z "$net_lines" ]] && return

    while IFS='|' read -r net_id net_name; do
        [[ -z "$net_id" ]] && continue
        echo "    NETWORK: $net_id ($net_name)"
        if $DELETE; then
            if openstack network delete "$net_id"; then
                log "    Deleted network $net_id"
            else
                warn "    Failed to delete network $net_id"
            fi
        fi
    done <<< "$net_lines"
}

delete_security_groups() {
    local project_id="$1"
    local project_name="$2"

    dbg "  Checking security groups in $project_name..."
    local sgs
    sgs=$(openstack security group list --project "$project_id" -f json 2>/dev/null || echo "[]")

    local sg_lines
    sg_lines=$(python3 -c "
import json, sys
for sg in json.load(sys.stdin):
    name = sg.get('Name', '')
    # Skip the default security group — can't delete it while project exists
    if name == 'default':
        continue
    print(sg.get('ID','') + '|' + name)
" <<< "$sgs")

    [[ -z "$sg_lines" ]] && return

    while IFS='|' read -r sg_id sg_name; do
        [[ -z "$sg_id" ]] && continue
        echo "    SECURITY GROUP: $sg_id ($sg_name)"
        if $DELETE; then
            if openstack security group delete "$sg_id"; then
                log "    Deleted security group $sg_id"
            else
                warn "    Failed to delete security group $sg_id"
            fi
        fi
    done <<< "$sg_lines"
}

# ---------------------------------------------------------------------------
# Main loop — iterate over each rally project and clean up resources
# ---------------------------------------------------------------------------
# Deletion order matters: servers first, then floating IPs, routers,
# ports, subnets, networks, security groups, volumes, images.
# This respects dependency ordering so deletions don't fail on conflicts.

TOTAL_RESOURCES=0

while read -r project_id project_name; do
    log "Processing project: $project_name ($project_id)"

    # Capture output so we can count resources found
    project_output=$(
        delete_servers       "$project_id" "$project_name"
        delete_floating_ips  "$project_id" "$project_name"
        delete_routers       "$project_id" "$project_name"
        delete_ports         "$project_id" "$project_name"
        delete_subnets       "$project_id" "$project_name"
        delete_networks      "$project_id" "$project_name"
        delete_security_groups "$project_id" "$project_name"
        delete_volumes       "$project_id" "$project_name"
        delete_images        "$project_id" "$project_name"
    )

    if [[ -n "$project_output" ]]; then
        echo "$project_output"
        count=$(echo "$project_output" | grep -c '^ ' || true)
        TOTAL_RESOURCES=$((TOTAL_RESOURCES + count))
    else
        log "  No resources found"
    fi

    # Delete the project itself
    echo "    PROJECT: $project_id ($project_name)"
    TOTAL_RESOURCES=$((TOTAL_RESOURCES + 1))
    if $DELETE; then
        if openstack project delete "$project_id"; then
            log "    Deleted project $project_id"
        else
            warn "    Failed to delete project $project_id"
        fi
    fi
    echo ""
done <<< "$RALLY_PROJECTS"

log "Total resources found: $TOTAL_RESOURCES"
if $DELETE; then
    log "Cleanup complete."
else
    log "Dry-run complete. Re-run with --delete to remove these resources."
fi
