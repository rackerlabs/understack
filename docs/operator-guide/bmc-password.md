# How to get the BMC password for a server

## TL;DR - Quick Commands

### Web UI

1. Go to: **argo-workflows-ui** -> **Workflow Templates** -> find and select **bmc-password** template
2. Click **Submit** → Enter BMC IP address → Click **Submit**
3. Check logs for the generated password

### CLI

```bash
# Submit workflow
argo -n argo-events submit --from workflowtemplate/bmc-password -p ip_address=192.168.1.100

# Check status
argo -n argo-events list

# Get password from logs (replace with actual workflow name)
argo -n argo-events logs <workflow-name>
```

### first line in log is password

```bash
# Submit and immediately follow logs
WORKFLOW=$(argo -n argo-events submit --from workflowtemplate/bmc-password -p ip_address=192.168.1.100 -o name) && argo -n argo-events logs $WORKFLOW -f
```

---

## Overview

The BMC Password workflow generates standard BMC passwords for given IP addresses using the Understack workflow system. This workflow retrieves the master secret from a Kubernetes secret and generates a deterministic password based on the BMC IP address.

## Prerequisites

- Access to the Argo Workflows cluster
- Valid BMC IP address
- Required secrets (`bmc-master`) must be available in the cluster

## Usage

### Web UI Usage

1. **Run Argo Workflow Template bmc-password**
    - find and select `bmc-password` workflow template
      - Click the **"Submit"** button on the workflow template page
      - Fill in the required parameters:
          - **ip_address**: Enter the BMC IP address (e.g., `192.168.1.100`)

2. **Monitor Execution**
    - After submission, you'll be redirected to the workflow execution page
    - Monitor the progress of your workflow in real-time
    - View logs by clicking on the workflow step

3. **View Results**
    - Once the workflow completes successfully, the generated password will be available in the logs
    - Navigate to the workflow step and check the container logs for the password output

### CLI Usage

#### Prerequisites for CLI

- Install Argo CLI: Follow the [official installation guide][argo-cli-install]
- Configure kubectl access to the cluster
- Ensure you have access to the `argo-events` namespace

#### Submit Workflow

```bash
# Basic usage
argo -n argo-events submit --from workflowtemplate/bmc-password \
  -p ip_address=<BMC_IP_ADDRESS>

# Example with specific IP
argo -n argo-events submit --from workflowtemplate/bmc-password \
  -p ip_address=192.168.1.100

# Submit with a custom workflow name
argo -n argo-events submit --from workflowtemplate/bmc-password \
  -p ip_address=10.0.1.50 \
  --name bmc-password-server-01
```

#### Monitor Workflow

```bash
# List all workflows
argo -n argo-events list

# Get specific workflow status
argo -n argo-events get <workflow-name>

# Follow workflow logs in real-time
argo -n argo-events logs <workflow-name> -f

# Get logs for completed workflow
argo -n argo-events logs <workflow-name>
```

#### Example Complete Session

```bash
# Submit the workflow
$ argo -n argo-events submit --from workflowtemplate/bmc-password -p ip_address=192.168.1.100
Name:                bmc-password-abc123
Namespace:           argo-events
ServiceAccount:      argo-workflow-sa
Status:              Pending
Created:             Mon Sep 24 07:30:00 UTC 2025

# Check status
$ argo -n argo-events get bmc-password-abc123
Name:                bmc-password-abc123
Namespace:           argo-events
ServiceAccount:      argo-workflow-sa
Status:              Succeeded
Created:             Mon Sep 24 07:30:00 UTC 2025
Started:             Mon Sep 24 07:30:05 UTC 2025
Finished:            Mon Sep 24 07:30:25 UTC 2025
Duration:            20 seconds

# Get the generated password from logs
$ argo -n argo-events logs bmc-password-abc123
bmc-password-abc123-bmc-password-1234567890: s8eso3LbI/bqZ4APxz1n
```

## Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `ip_address` | string | Yes | BMC IP address for password generation | `192.168.1.100` |

## Output

The workflow outputs the generated BMC password to the container logs. The password is printed as a single line and can be retrieved from the workflow logs.

**Example Output:**

```text
xyzso3LbI/bqZ4APx123
```

[argo-cli-install]: https://argoproj.github.io/argo-workflows/cli/
