# OpenStack CLI

## Installation

The easiest way to install the OpenStack CLI is to utilize your
OS packages. But if you want to install it manually you will need
to already have Python on your system.

<!-- markdownlint-capture -->
<!-- markdownlint-disable MD046 -->
=== "Ubuntu or Debian"

    ``` bash
    apt install python3-openstackclient
    # TODO: install keystoneauth-websso
    ```

=== "macOS"

    ``` bash
    brew install openstackclient
    ```

=== "pip"

    ``` bash
    # create Python virtualenv at $HOME/.openstack
    python -m venv $HOME/.openstack
    # install the tools
    $HOME/.openstack/bin/pip install python-openstackclient 'python-ironicclient[cli]' keystoneauth-websso

    # create a binary wrapper to the virtualenv
    mkdir -p $HOME/.bin
    cat <<- "EOF" > $HOME/.bin/openstack
    #!/bin/sh
    source $HOME/.openstack/bin/activate
    exec $HOME/.openstack/bin/openstack "$@"
    EOF
    chmod +x $HOME/.bin/openstack

    # add it to our PATH
    export PATH="$HOME/.bin:$PATH"

    # make sure we always have it
    cat <<- "EOF" >> $HOME/.bashrc
    export PATH="$HOME/.bin:$PATH"
    EOF
    ```
<!-- markdownlint-restore -->

## Configuration

The easiest way to configure your client is via `clouds.yaml`.

```yaml title="$HOME/.config/openstack/clouds.yaml"
clouds:
  understack:
    auth_type: v3websso
    identity_provider: sso
    protocol: openid
    auth:
      auth_url: https://your.endpoint.url/v3
      project_domain_name: mydomain
      project_name: myproject
```

With the above configuration in `$HOME/.config/openstack/clouds.yaml` you
will be able to run the OpenStack CLI as follows:

```bash
openstack --os-cloud understack <sub-command-here>
```

Or you can set the `OS_CLOUD` environment variable once and shorten the
command as follows:

```bash
export OS_CLOUD=understack
openstack <sub-command-here>
```
