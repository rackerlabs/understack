# understackctl

`understackctl` is the CLI tool for managing UnderStack deployments. It handles deployment repository scaffolding, secret generation, hardware definitions, node lifecycle workflows, and more.

## Installation

### Using go install

If you have Go 1.24+ installed, you can install directly:

```bash
go install github.com/rackerlabs/understack/go/understackctl@latest
```

This places the binary in your `$GOPATH/bin` (or `$HOME/go/bin` by default). Make sure that directory is in your `PATH`.

### From source

Requires Go 1.24+.

```bash
git clone https://github.com/rackerlabs/understack.git
cd understack/go/understackctl
make build
```

The binary will be at `build/understackctl/understackctl`. Add it to your `PATH` or copy it somewhere convenient:

```bash
cp build/understackctl/understackctl /usr/local/bin/
```

### Cross-platform builds

Build for Linux, macOS, and Windows (amd64/arm64/386):

```bash
make build-all
```

Outputs are placed in `build/` as platform-specific directories. To create distributable archives:

```bash
make package-all
```

This produces `.tar.gz` files (Linux/macOS) and `.zip` files (Windows).

To generate SHA-256 checksums for all archives:

```bash
make checksums
```

### From release binaries

Download a pre-built binary from the [GitHub Releases](https://github.com/rackerlabs/understack/releases) page, extract it, and place it in your `PATH`.

## Prerequisites

Depending on which commands you use, you may need:

- `kubectl` — Kubernetes cluster access
- `helm` (3.8+) — Helm chart rendering
- `kubeseal` — Sealed Secrets encryption
- `argo` — Argo Workflows CLI (for node commands)
- `git` — deploy repo operations
- A valid kubeconfig pointing at your target cluster

## Environment Variables

| Variable | Used by | Description |
|---|---|---|
| `UC_DEPLOY` | `deploy`, `device-type`, `flavor` | Path to the deployment repository |
| `DEPLOY_NAME` | secret generators, `quickstart` | Name of the deployment / cluster |

## Commands

### deploy

Manage the deployment repository structure and configuration. All subcommands accept `--deploy-repo` (or the `UC_DEPLOY` env var) to specify the path to your deploy repo.

#### deploy init

```bash
understackctl deploy init <cluster-name> [--type global|site|aio] [--git-remote origin]
```

Create a new cluster directory with a `deploy.yaml` configuration file. Fetches the current component list from the UnderStack repository and populates the global and/or site sections based on the cluster type.

- `--type` (default: `aio`) — Cluster type. `global` includes only global components, `site` includes only site components, `aio` includes both.
- `--git-remote` (default: `origin`) — Git remote name used to detect the deploy repo URL.

#### deploy update

```bash
understackctl deploy update <cluster-name>
```

Sync the cluster directory with `deploy.yaml`. Creates directories, `kustomization.yaml`, and `values.yaml` for newly enabled components. Removes directories for disabled components.

#### deploy check

```bash
understackctl deploy check <cluster-name>
```

Validate that every enabled component has the required `kustomization.yaml` and `values.yaml` files. Reports any missing files and exits with an error if validation fails.

#### deploy render

```bash
understackctl deploy render <cluster-name> [--chart-path <path>] [--version main]
```

Preview the rendered ArgoCD Applications by running `helm template` against the cluster's `deploy.yaml`. By default it clones the UnderStack repo to get the chart; use `--chart-path` to point at a local chart instead.

- `--chart-path` — Path to a local ArgoCD Helm chart directory. If omitted, the chart is cloned from the UnderStack repo.
- `--version` (default: `main`) — Git ref (branch or tag) to use when cloning the default chart.

#### deploy enable

```bash
understackctl deploy enable <cluster-name> <component-name> --type global|site|aio
```

Enable a component in the cluster's `deploy.yaml`. The `--type` flag is required and determines which section(s) the component is added to. Using `aio` enables it in both `global` and `site`.

#### deploy disable

```bash
understackctl deploy disable <cluster-name> <component-name> --type global|site|aio
```

Disable a component in the cluster's `deploy.yaml`. The component directory is not removed until `deploy update` is run.

#### deploy image-set

```bash
understackctl deploy image-set <cluster-name> <version> [--no-digest]
```

Walk all YAML files in the cluster directory and update UnderStack container image tags to the specified version. Also updates `?ref=vX.Y.Z` references in `kustomization.yaml` files. By default, the sha256 digest is resolved from the container registry and pinned alongside the tag.

- `--no-digest` — Write the tag only, skip the registry digest lookup.

### device-type

Manage hardware device type definitions. Requires `UC_DEPLOY` to be set.

#### device-type add

```bash
understackctl device-type add <file>
```

Validate a device-type YAML file against the JSON schema and copy it into the deploy repo's `hardware/device-types/` directory. Updates the `kustomization.yaml` configMapGenerator entry automatically.

#### device-type validate

```bash
understackctl device-type validate <file>
```

Validate a device-type YAML file against the JSON schema without adding it to the deployment. Useful for checking definitions before committing.

#### device-type delete

```bash
understackctl device-type delete <name>
```

Remove a device-type definition by name and update the `kustomization.yaml` accordingly.

#### device-type list

```bash
understackctl device-type list
```

List all device-type definitions found in `hardware/device-types/`.

#### device-type show

```bash
understackctl device-type show <name>
```

Display detailed information about a device-type including class, manufacturer, model, interfaces, and resource classes.

### flavor

Manage hardware flavor definitions for node matching. Requires `UC_DEPLOY` to be set.

#### flavor add

```bash
understackctl flavor add <file>
```

Validate a flavor YAML file against the JSON schema and copy it into `hardware/flavors/`. Updates the `kustomization.yaml` configMapGenerator entry.

#### flavor validate

```bash
understackctl flavor validate <file>
```

Validate a flavor definition against the JSON schema without adding it.

#### flavor delete

```bash
understackctl flavor delete <name>
```

Remove a flavor definition by name and update `kustomization.yaml`.

#### flavor list

```bash
understackctl flavor list
```

List all flavor definitions in `hardware/flavors/`.

#### flavor show

```bash
understackctl flavor show <name>
```

Display detailed information about a flavor including its resource class and trait requirements.

### node

Manage node lifecycle workflows by wrapping Argo Workflows.

#### node enroll-server

```bash
understackctl node enroll-server <ip-address> [flags]
```

Submit the `enroll-server` Argo workflow for a bare metal node. Requires the `argo` CLI to be installed and a valid kubeconfig.

- `--old-password` — Existing node password (e.g. BMC password).
- `--firmware-update` — Perform a firmware update during enrollment.
- `--raid-configure` — Configure RAID during enrollment.
- `--external-cmdb-id` — External CMDB identifier for the node.
- `--log` — Stream workflow logs after submission.

#### node inspect-server

```bash
understackctl node inspect-server <node-id> [--log]
```

Submit the `inspect-server` Argo workflow for a node. Takes a node ID (not an IP address).

- `--log` — Stream workflow logs after submission.

### node-update

```bash
understackctl node-update
```

Label all Kubernetes cluster nodes with `openstack-control-plane=enabled`. Skips nodes that already have the label. Requires a valid kubeconfig.

### nautobotop

Nautobot Operator operations.

#### nautobotop resync

```bash
understackctl nautobotop resync [--name <cr-name>] [--operator <namespace/name>]
```

Force a re-sync of the Nautobot custom resource by clearing its status and performing a rollout restart of the operator deployment. If `--name` or `--operator` are omitted, the command auto-detects them from the cluster and prompts for selection if multiple are found.

- `--name`, `-n` — Name of the Nautobot CR (auto-detected if omitted).
- `--operator` — Operator deployment as `namespace/name` (auto-detected if omitted).

### Secret Generation Commands

These commands generate Kubernetes Sealed Secrets and configuration files for various services. They typically require `DEPLOY_NAME`, `DNS_ZONE`, and a running cluster with `kubeseal` available.

#### argocd-secrets

```bash
understackctl argocd-secrets
```

Generate ArgoCD repository and cluster secrets. Uses `DEPLOY_NAME`, `UC_DEPLOY_GIT_URL`, `UC_DEPLOY_SSH_FILE`, and `DNS_ZONE` environment variables.

#### certmanager-secrets

```bash
understackctl certmanager-secrets
```

Generate a cert-manager ClusterIssuer manifest. Uses `UC_DEPLOY_EMAIL` and `DNS_ZONE`.

#### dex-secrets

```bash
understackctl dex-secrets
```

Generate Dex OAuth2/OIDC client secrets for nautobot, argo, argocd, keystone, and grafana. Each client gets a randomly generated 32-character secret.

#### openstack-secrets

```bash
understackctl openstack-secrets
```

Generate a MariaDB sealed secret for the OpenStack namespace with random root and user passwords.

#### other-secrets

```bash
understackctl other-secrets
```

Generate secrets for keystone, ironic, placement, neutron, nova, glance, and horizon. Creates per-service sealed secrets for RabbitMQ, Keystone, and database passwords. Also generates the `secret-openstack.yaml` endpoints configuration file with all passwords populated. Attempts to load existing passwords from the cluster before generating new ones.

#### helm-config

```bash
understackctl helm-config
```

Generate Helm `values.yaml` files for dex, glance, ironic, and rook-cluster in the deploy repo. Uses `DEPLOY_NAME` and `DNS_ZONE`.

### quickstart

```bash
understackctl quickstart
```

Run all setup steps in sequence: node labeling, ArgoCD secrets, cert-manager secrets, Dex secrets, OpenStack service secrets, MariaDB secrets, and Helm configs. Requires `kubeseal` to be installed and all relevant environment variables to be set (`DEPLOY_NAME`, `UC_DEPLOY_GIT_URL`, `UC_DEPLOY_SSH_FILE`, `DNS_ZONE`, `UC_DEPLOY_EMAIL`).

## Development

To add a new command, create a constructor function:

```go
func NewCmdMyCommand() *cobra.Command {
    return &cobra.Command{
        Use:   "mycommand",
        Short: "This will run my command",
        Run:   myCommandFunction,
    }
}
```

Then register it in `cmd/root/root.go`:

```go
func init() {
    rootCmd.AddCommand(mypkg.NewCmdMyCommand())
}
```

## Contributing

If you find any issues or have suggestions for improvements, please open an issue on the [GitHub repository](https://github.com/rackerlabs/understack).
