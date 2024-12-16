# terraform multi node example

In this example we will build multiple servers (default 2) connected
to a network that is created. Certain things can be customized via
terraform variables, check the `variables.tf` for details.

## pre-reqs

1. You must have a project and be able to authenticate to it. Please see
   the [User Guide](https://rackerlabs.github.io/understack/user-guide/)
   to get your CLI setup.
2. You must have the `terraform` CLI installed.

## credentials

Terraform does not support the SSO authentication that is used by UnderStack
so you must create an [Application Credential](https://docs.openstack.org/keystone/latest/user/application_credentials.html)
for Terraform to use.

You can follow the following to generate it assuming your `openstack` is
able to authenticate to your project.

```sh
# creates an application credential called "terraform-cred"
openstack application credential create terraform-cred
# terraform will read these environment variables
export OS_APPLICATION_CREDENTIAL_ID=${FROM_ABOVE}
export OS_APPLICATION_CREDENTIAL_SECRET=${FROM_ABOVE}
```

## Executing the example

You must have `terraform` install the OpenStack provider. To do so
run the following:

```sh
terraform init
```

This is non-destructive and can be run multiple times.


Now you can create the resources with the following:

```sh
terraform apply
```
