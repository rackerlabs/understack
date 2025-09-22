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
  my-site:
    auth_type: v3websso
    identity_provider: sso
    protocol: openid
    auth:
      auth_url: {{ config.extra.auth_url }}
      project_domain_name: Default
      project_name: myproject
    region_name: {{ config.extra.region_name }}
```

<!-- markdownlint-capture -->
<!-- markdownlint-disable MD046 -->
!!! Note

    The Ironic nodes will be in the `infra` domain and the `baremetal` project.
<!-- markdownlint-restore -->

With the above configuration in `$HOME/.config/openstack/clouds.yaml` you
will be able to run the OpenStack CLI as follows:

```bash
openstack --os-cloud my-site <sub-command-here>
```

Or you can set the `OS_CLOUD` environment variable once and shorten the
command as follows:

```bash
export OS_CLOUD=my-site
openstack <sub-command-here>
```

### Application Credentials

Users can create application credentials to allow their applications to authenticate to keystone.
This is useful when using tooling such as `terraform` and `ansible` to programmatically build infrastructure.

To create an application credential:

```sh
# creates an application credential called "application-credential"
openstack application credential create application-credential
# terraform and ansible will read these environment variables
export OS_APPLICATION_CREDENTIAL_ID=${FROM_ABOVE}
export OS_APPLICATION_CREDENTIAL_SECRET=${FROM_ABOVE}
```

As a scriptable command:

```sh
openstack application credential create terraform-cred \
    -f shell -c id -c secret --prefix 'export OS_APPLICATION_CREDENTIAL_' \
    | sed -e 's/_id/_ID/' -e 's/_secret/_SECRET/' > tf-creds.env
source tf-creds.env
```

You can also add a section to your `$HOME/.config/openstack/clouds.yaml` OpenStack configuration file.
Note the auth_type and auth options are slightly different than in the above SSO example.

```yaml title="$HOME/.config/openstack/clouds.yaml"
clouds:
  my-site-app:
    auth_type: v3applicationcredential
    auth:
      auth_url: {{ config.extra.auth_url }}
      application_credential_id: ${FROM_ABOVE}
      application_credential_secret: ${FROM_ABOVE}
    region_name: {{ config.extra.region_name }}
```

The `openstack` cli, `terraform` and `ansible` can all use application credentials and
the `OS_CLOUD` environment variable:

```bash
export OS_CLOUD=my-site-app
```

There are a number of additional features and options available in the OpenStack documentation:
<https://docs.openstack.org/keystone/latest/user/application_credentials.html>
