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
    --from-literal=password="$(./scripts/pwgen.sh)" \
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
    --from-literal=NAUTOBOT_REDIS_PASSWORD="$(./scripts/pwgen.sh)" \
    --from-literal=NAUTOBOT_SECRET_KEY="$(./scripts/pwgen.sh)" \
    --from-literal=NAUTOBOT_SUPERUSER_API_TOKEN="$(./scripts/pwgen.sh)" \
    --from-literal=NAUTOBOT_SUPERUSER_PASSWORD="$(./scripts/pwgen.sh)" \
    > secret-nautobot-env.yaml

kubectl --namespace nautobot \
    create secret generic nautobot-redis \
    --dry-run \
    -o yaml \
    --type Opaque \
    --from-literal=redis-password="$(yq e '.data.NAUTOBOT_REDIS_PASSWORD' secret-nautobot-env.yaml | base64 -d)" \
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

## Generate Kustomize for the Install

Now generate the kustomize for this.

```bash
cd components/01-secrets
kustomize create --autodetect
cd ../..
```

At this point you can return to the main README.
