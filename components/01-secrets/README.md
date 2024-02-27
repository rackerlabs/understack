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
kubectl --namespace openstack \
        create secret generic keystone-credential-keys \
        --type Opaque \
        --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
        --dry-run -o yaml > secret-keystone-credential-keys.yaml
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

## Generate Kustomize for the Install

Now generate the kustomize for this.

```bash
cd components/01-secrets
kustomize create --autodetect
cd ../..
```

At this point you can return to the main README.
