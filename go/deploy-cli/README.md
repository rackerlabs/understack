# undercloud-deploy-cli

Undercloud Deploy cli helps quickly generate undercloud-deploy config files.


## How to use.

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

* Run

```
go run *.go init
go run *.go help
```

* Commit all changes to the undercloud-deploy repo in your branch


## Contributing

If you find any issues or have suggestions for improvements, please open an issue on the [GitHub repository](https://github.com/rackerlabs/understack).
