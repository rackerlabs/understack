# understackctl

understackctl is a CLI tool for managing UnderStack deployments.

## Commands

### deploy

Manage deployment repository structure and configuration.

```bash
# Initialize a new cluster configuration
understackctl deploy init <cluster-name> --type <global|site|aio>

# Sync manifest directories with deploy.yaml
understackctl deploy update <cluster-name>

# Validate configuration
understackctl deploy check <cluster-name>
```

See the [Deploy Guide](https://rackerlabs.github.io/understack/deploy-guide/deploy-repo/) for details.

### Other Commands

Run `understackctl --help` to see all available commands.

## Build

* Local build: `make build` (builds for your local OS)
* Cross-platform build: `make build-all` (builds for Linux, macOS, Windows)

## Development

* To add a new command, create a function like this.

```go
func NewCmdMyCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "mycommand",
		Short: "This will run my command",
		Long:  "This will run my command",
		Run:   myCommandFunction,
	}
}
```

* After that register it to `cmd/root/root.go`

```go
func init() {
	rootCmd.AddCommand(deploy.NewCmdMyCommand())
}
```

## Contributing

If you find any issues or have suggestions for improvements, please open an issue on the [GitHub repository](https://github.com/rackerlabs/understack).
