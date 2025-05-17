# Adding Git Repos

In your variables you'll need to define something like:

```yaml
nb_git_repos:
  device_types:
    name: Device Types
    remote_url: https://github.com/RSS-Engineering/undercloud-nautobot-device-types.git
    branch: main
    secrets_group: gh_dev_type_pat
```

Where the `key` is the unique slug and the `secrets_group` is the reference to
a `secrets_group` you've defined in the variable `nb_secrets_groups`.
