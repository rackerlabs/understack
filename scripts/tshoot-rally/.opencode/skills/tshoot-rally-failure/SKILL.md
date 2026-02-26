---
name: tshoot-rally-failure
description: Troubleshoot Rally build failures by analyzing GitHub Actions and Grafana logs
license: MIT
compatibility: opencode
metadata:
  team: understack
  category: troubleshooting
---

## What I do

I analyze Rally build failures by:
- Fetching GitHub Actions job logs
- Extracting server and instance information
- Collecting logs from nova-compute-ironic, ironic-conductor, and neutron-server
- Displaying logs with colored timestamps and log levels (ERROR in red, WARNING in yellow, INFO in green)
- Providing Grafana URLs for deeper investigation

## When to use me

Use this skill when:
- A Rally test fails in GitHub Actions
- You need to investigate OpenStack deployment issues
- You want to see correlated logs across multiple services (Nova, Ironic, Neutron)

## Requirements

You must have these environment variables set:
- `GITHUB_TOKEN` - GitHub personal access token for fetching job logs
- `GRAFANA_TOKEN` - Grafana API token for fetching service logs

## How to use me

Provide the GitHub Actions job URL as an argument:

```bash
./fetch_gh_logs.py https://github.com/RSS-Engineering/undercloud-deploy/actions/runs/12345/job/67890
```

## What you'll get

1. Extracted server data (server_id, network_id, timestamps, cluster)
2. Baremetal node ID extracted from nova-compute logs
3. Three sets of logs with colored output:
   - nova-compute-ironic logs (filtered by server_id)
   - ironic-conductor logs (filtered by baremetal_node_id)
   - neutron-server logs (filtered by baremetal_node_id)
4. Grafana URLs for each log source
5. All logs saved to temp files for further analysis

## Common issues to look for

- **Neutron binding failures**: Port binding errors in neutron-server logs
- **Ironic provisioning failures**: Deploy step failures in ironic-conductor logs
- **Nova spawn failures**: Instance deployment errors in nova-compute logs
- **Network configuration issues**: VIF attachment or network setup problems
