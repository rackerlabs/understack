# understackctl

understackctl is a CLI that helps quickly generate a deployment repository.

## How to use

> Please make sure that you have kubeseal binary installed your system https://github.com/bitnami-labs/sealed-secrets

* Export all these env

```sh
export UC_DEPLOY="<full_local_path_to_undercloud_deploy_repo>"
export DEPLOY_NAME="<cluster_name>"
export UC_DEPLOY_GIT_URL=git@github.com:RSS-Engineering/undercloud-deploy.git
export UC_DEPLOY_SSH_FILE=<path_to_ssh_private_key_file>
export DNS_ZONE=<cluster_name>.dev.undercloud.rackspace.net
export UC_DEPLOY_EMAIL="<your_email>"
export UC_AIO=yes
```

* Quick Run

```
go run *.go quickstart
go run *.go help
```

* Commit all changes to the undercloud-deploy repo in your branch

## Build

* Local build `make build` ( this will only build binary for you local os ).
* Cross-Platform build `make build-all` ( build for linux-mac-windows )

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
