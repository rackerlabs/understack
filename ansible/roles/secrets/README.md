# Adding Secrets

In your variables you'll need to define something like:

```yaml
secrets_nb_secrets_groups:
  gh_dev_type_pat:
    - access_type: "HTTP(S)"
      secret_type: token
      name: test_pw
      provider: pwsafe
      parameters:
        project: "37639"
        cred: "329557"
        field: password
  tacacs_user_a_http:
    - access_type: "HTTP(S)"
      secret_type: "username"
      name: tacacs_user
      provider: pwsafe
      parameters:
        project: "38518"
        cred: "336939"
        field: username
    - access_type: "HTTP(S)"
      secret_type: "password"
      name: tacacs_pass
      provider: pwsafe
      parameters:
        project: "38518"
        cred: "336939"
        field: password
  tacacs_user_b_http:
    - access_type: "HTTP(S)"
      secret_type: "username"
      name: tacacs_user
      provider: pwsafe
      parameters:
        project: "38518"
        cred: "336940"
        field: username
    - access_type: "HTTP(S)"
      secret_type: "password"
      name: tacacs_pass
      provider: pwsafe
      parameters:
        project: "38518"
        cred: "336940"
        field: password
```

Where the `key` is the unique reference which can be used in other places
like Git Repos.
