# undercloud-deploy-cli

Undercloud Deploy cli helps quickly generate undercloud-deploy config files.

## How to use.

* Download the latest release from [GitHub](https://github.com/rackerlabs/understack/go/deploy-cli/releases)

**MacOS**
[Binary](https://github.com/rackerlabs/understack/go/deploy-cli/releases/latest/download/undercloud-deploy-cli_Darwin_all.tar.gz) ( Multi-Architecture )

**Linux (Binaries)**
[amd64](https://github.com/rackerlabs/understack/go/deploy-cli/releases/latest/download/undercloud-deploy-cli_Linux_x86_64.tar.gz) | [arm64](https://github.com/rackerlabs/understack/go/deploy-cli/releases/latest/download/undercloud-deploy-cli_Linux_arm64.tar.gz) | [i386](https://github.com/rackerlabs/understack/go/deploy-cli/releases/latest/download/undercloud-deploy-cli_Linux_i386.tar.gz)

**Windows (Exe)**
[amd64](https://github.com/rackerlabs/understack/go/deploy-cli/releases/latest/download/undercloud-deploy-cli_Windows_x86_64.zip) | [arm64](https://github.com/rackerlabs/understack/go/deploy-cli/releases/latest/download/undercloud-deploy-cli_Windows_arm64.zip) | [i386](https://github.com/rackerlabs/understack/go/deploy-cli/releases/latest/download/undercloud-deploy-cli_Windows_i386.zip)

* Export these all these env variables to your shell or system env

```sh
export UC_DEPLOY="<full_local_path_to_undercloud_deploy_repo>"
export DEPLOY_NAME="<cluster_name>"
export UC_DEPLOY_GIT_URL=git@github.com:RSS-Engineering/undercloud-deploy.git
export UC_DEPLOY_SSH_FILE=<path_to_ssh_private_key_file>
export DNS_ZONE=<cluster_name>.dev.undercloud.rackspace.net
export UC_DEPLOY_EMAIL="<your_email>"
export UC_AIO=yes
```

* Run the following command create config files

```sh
./undercloud-deploy-cli all
```

* Commit all changes to the undercloud-deploy repo in your branch


## Contributing

If you find any issues or have suggestions for improvements, please open an issue on the [GitHub repository](https://github.com/rackerlabs/understack/go/deploy-cli/issues).
