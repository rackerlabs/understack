#!/bin/bash -ex

cd $(git rev-parse --show-toplevel)

kubectl --namespace openstack \
    create secret generic mariadb \
    --dry-run \
    -o yaml \
    --type Opaque \
    --from-literal=root-password="$(./scripts/pwgen.sh)" \
    --from-literal=password="$(./scripts/pwgen.sh)" \
    > secret-mariadb.yaml

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

kubectl --namespace openstack \
    create secret generic keystone-rabbitmq-password \
    --type Opaque \
    --from-literal=username="keystone" \
    --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
    --dry-run -o yaml \
    > secret-keystone-rabbitmq-password.yaml
kubectl --namespace openstack \
    create secret generic keystone-db-password \
    --type Opaque \
    --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
    --dry-run -o yaml \
    > secret-keystone-db-password.yaml
kubectl --namespace openstack \
    create secret generic keystone-admin \
    --type Opaque \
    --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
    --dry-run -o yaml \
    > secret-keystone-admin.yaml
kubectl --namespace openstack \
    create secret generic keystone-credential-keys \
    --type Opaque \
    --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
    --dry-run -o yaml \
    > secret-keystone-credential-keys.yaml

kubeseal \
    --scope cluster-wide \
    --allow-empty-data \
    -o yaml \
    -f secret-mariadb.yaml \
    -w components/01-secrets/encrypted-mariadb.yaml

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

for skrt in $(find . -name "secret-keystone*.yaml" -depth 1); do
    encskrt=$(echo "${skrt}" | sed -e 's/secret-/components\/01-secrets\/encrypted-/')
    kubeseal \
        --scope cluster-wide \
        --allow-empty-data \
        -o yaml \
        -f "${skrt}" \
        -w "${encskrt}"
done

cd components/01-secrets/
rm -f kustomization.yaml
kustomize create --autodetect
cd ../..
