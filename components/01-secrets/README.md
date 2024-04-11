# Generate Secrets

Secrets will be encrypted to your specific cluster and not re-usable so we'll do some setup for that.

The unencrypted (just base64 encoded) secrets will be in `secret-$NAME.yaml` files while the
encrypted secrets, that can be committed to a public git repo, will be in `encrypted-$NAME.yaml`

There's a helper script in this repo in `scripts/pwgen.sh` which creates a random 32 character password
that will be used. You can create these with any other source as well. If you have them stored in
another location then you can delete everything here. Otherwise, once they're encrypted you cannot
decrypt them (but if you have access to the k8s cluster you can grab them there).

You **MUST** run these commands from the top-level of the repo.

## MariaDB

Let's generate the MariaDB root creds.

```bash
kubectl --namespace openstack \
    create secret generic mariadb \
    --dry-run \
    -o yaml \
    --type Opaque \
    --from-literal=root-password="$(./scripts/pwgen.sh)" \
    > secret-mariadb.yaml
```

And encrypt it.

```bash
kubeseal \
    --scope cluster-wide \
    --allow-empty-data \
    -o yaml \
    -f secret-mariadb.yaml \
    -w components/01-secrets/encrypted-mariadb.yaml
```

## Nautobot

Now generate the Nautobot env secrets and the Redis (TODO: operator)

```bash
kubectl --namespace nautobot \
    create secret generic nautobot-env \
    --dry-run \
    -o yaml \
    --type Opaque \
    --from-literal=NAUTOBOT_SECRET_KEY="$(./scripts/pwgen.sh)" \
    --from-literal=NAUTOBOT_SUPERUSER_API_TOKEN="$(./scripts/pwgen.sh)" \
    --from-literal=NAUTOBOT_SUPERUSER_PASSWORD="$(./scripts/pwgen.sh)" \
    > secret-nautobot-env.yaml

kubectl --namespace nautobot \
    create secret generic nautobot-redis \
    --dry-run \
    -o yaml \
    --type Opaque \
    --from-literal=redis-password="$(./scripts/pwgen.sh)" \
    > secret-nautobot-redis.yaml
```

```bash
# This secret needs to be synchronized in both namespaces
NAUTOBOT_SSO_SECRET=$(./scripts/pwgen.sh)
for ns in nautobot dex; do
  kubectl --namespace $ns \
    create secret generic nautobot-sso \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=client-secret="$NAUTOBOT_SSO_SECRET" \
    > secret-nautobot-sso-$ns.yaml
done
unset NAUTOBOT_SSO_SECRET
```

Let's encrypt them.

```bash
kubeseal \
    --scope cluster-wide \
    --allow-empty-data \
    -o yaml \
    -f secret-nautobot-env.yaml \
    -w components/01-secrets/encrypted-nautobot-env.yaml

kubeseal \
    --scope cluster-wide \
    --allow-empty-data \
    -o yaml \
    -f secret-nautobot-redis.yaml \
    -w components/01-secrets/encrypted-nautobot-redis.yaml

for ns in nautobot dex; do
  kubeseal \
    --scope cluster-wide \
    --allow-empty-data \
    -o yaml \
    -f secret-nautobot-sso-$ns.yaml \
    -w components/01-secrets/encrypted-nautobot-sso-$ns.yaml
done
```

## Keystone

Generate the necessary secrets for OpenStack Keystone.

```bash
kubectl --namespace openstack \
        create secret generic keystone-rabbitmq-password \
        --type Opaque \
        --from-literal=username="keystone" \
        --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
        --dry-run -o yaml > secret-keystone-rabbitmq-password.yaml
kubectl --namespace openstack \
        create secret generic keystone-db-password \
        --type Opaque \
        --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
        --dry-run -o yaml > secret-keystone-db-password.yaml
kubectl --namespace openstack \
        create secret generic keystone-admin \
        --type Opaque \
        --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
        --dry-run -o yaml > secret-keystone-admin.yaml
```

Now let's seal them.

```bash
for skrt in $(find . -name "secret-keystone*.yaml" -depth 1); do
    encskrt=$(echo "${skrt}" | sed -e 's/secret-/components\/01-secrets\/encrypted-/')
    kubeseal \
        --scope cluster-wide \
        --allow-empty-data \
        -o yaml \
        -f "${skrt}" \
        -w "${encskrt}"
done
```

## Ironic

Generate the necessary secrets for OpenStack Ironic.

```bash
kubectl --namespace openstack \
        create secret generic ironic-rabbitmq-password \
        --type Opaque \
        --from-literal=username="ironic" \
        --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
        --dry-run=client -o yaml > secret-ironic-rabbitmq-password.yaml
kubectl --namespace openstack \
        create secret generic ironic-db-password \
        --type Opaque \
        --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
        --dry-run=client -o yaml > secret-ironic-db-password.yaml
kubectl --namespace openstack \
        create secret generic ironic-keystone-password \
        --type Opaque \
        --from-literal=username="ironic" \
        --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
        --dry-run=client -o yaml > secret-ironic-keystone-password.yaml
```

Now let's seal them.

```bash
for skrt in $(find . -maxdepth 1-name "secret-ironic*.yaml"); do
    encskrt=$(echo "${skrt}" | sed -e 's/secret-/components\/01-secrets\/encrypted-/')
    kubeseal \
        --scope cluster-wide \
        --allow-empty-data \
        -o yaml \
        -f "${skrt}" \
        -w "${encskrt}"
done

```
## Azure SSO authentication

Setting up Understack for Azure backed authentication involves two steps:
1. Creating a Kubernetes secret that contains credentials to talk to AAD.
2. Updating Dexidp `Application` to use Azure settings/values

Detailed steps are:

First, you need to obtain necessary credentials from [PasswordSafe](https://passwordsafe.corp.rackspace.com/projects/37639/credentials/329301/). Replace the `<CLIENTID>`, `<CLIENTSECRET>` and `<ISSUER>` in the following command.

PasswordSafe mappings:
- `<CLIENTID>` is stored as `Username`
- `<CLIENTSECRET>` is stored in `Password` field
- `<ISSUER>` needs to be constructed. The value should be
`https://login.microsoftonline.com/<APPID>/v2.0`, where `<APPID>` is stored in
PasswordSafe under `Hostname` field. Pay particular attention to `/v2.0` at the
end of URL and don't add trailing slash. Example value would be:
`https://login.microsoftonline.com/1234abcd-1234-0000-beef-12345678900a/v2.0`

```bash
kubectl --namespace dex \
    create secret generic azure-sso --dry-run=client \
    --from-literal=client-id=<CLIENTID> \
    --from-literal=client-secret=<CLIENTSECRET> \
    --from-literal=issuer=<ISSUER> \
    -o yaml > secret-azure-sso.yaml

kubeseal \
  --scope cluster-wide \
  --allow-empty-data \
  -o yaml \
  -f secret-azure-sso.yaml \
  -w components/01-secrets/encrypted-azure-sso.yaml
```

The second part of the setup involves switching Dex to use the Azure backend.
This can be done by executing:

```shell
argocd app set argocd/dexidp --values '$values/components/dexidp/values-azure.yaml'
```


## Generate Kustomize for the Install

Now generate the kustomize for this.

```bash
cd components/01-secrets
kustomize create --autodetect
cd ../..
```

At this point you can return to the main README.
