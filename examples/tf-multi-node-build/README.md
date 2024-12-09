# terraform example


## credentials

```sh
openstack application credential create terraform-cred --restricted
export OS_APPLICATION_CREDENTIAL_ID=${FROM_ABOVE}
export OS_APPLICATION_CREDENTIAL_SECRET=${FROM_ABOVE}
```

## Running it

```
terraform init
terraform apply
```
