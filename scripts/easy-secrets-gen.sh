#!/bin/bash -ex

cd $(git rev-parse --show-toplevel)

kubectl --namespace openstack \
    create secret generic mariadb \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=root-password="$(./scripts/pwgen.sh)" \
    --from-literal=password="$(./scripts/pwgen.sh)" \
    > secret-mariadb.yaml

kubectl --namespace nautobot \
    create secret generic nautobot-env \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=NAUTOBOT_SECRET_KEY="$(./scripts/pwgen.sh)" \
    --from-literal=NAUTOBOT_SUPERUSER_API_TOKEN="$(./scripts/pwgen.sh)" \
    --from-literal=NAUTOBOT_SUPERUSER_PASSWORD="$(./scripts/pwgen.sh)" \
    > secret-nautobot-env.yaml

kubectl --namespace nautobot \
    create secret generic nautobot-redis \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=redis-password="$(./scripts/pwgen.sh)" \
    > secret-nautobot-redis.yaml

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

ARGO_SSO_SECRET=$(./scripts/pwgen.sh)
for ns in argo argo-events argocd dex; do
  kubectl --namespace $ns \
    create secret generic argo-sso \
    --dry-run=client \
    -o yaml \
    --type Opaque \
    --from-literal=client-secret="$ARGO_SSO_SECRET" \
    --from-literal=client-id=argo \
    > secret-argo-sso-$ns.yaml
done
unset ARGO_SSO_SECRET


kubectl --namespace openstack \
    create secret generic keystone-rabbitmq-password \
    --type Opaque \
    --from-literal=username="keystone" \
    --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
    --dry-run=client -o yaml \
    > secret-keystone-rabbitmq-password.yaml
kubectl --namespace openstack \
    create secret generic keystone-db-password \
    --type Opaque \
    --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
    --dry-run=client -o yaml \
    > secret-keystone-db-password.yaml
kubectl --namespace openstack \
    create secret generic keystone-admin \
    --type Opaque \
    --from-literal=password="$($(git rev-parse --show-toplevel)/scripts/pwgen.sh)" \
    --dry-run=client -o yaml \
    > secret-keystone-admin.yaml

# ironic credentials
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

for skrt in $(find . -maxdepth 1 -name "secret-keystone*.yaml" -o -name "secret-ironic*.yaml"); do
    encskrt=$(echo "${skrt}" | sed -e 's/secret-/components\/01-secrets\/encrypted-/')
    kubeseal \
        --scope cluster-wide \
        --allow-empty-data \
        -o yaml \
        -f "${skrt}" \
        -w "${encskrt}"
done

for ns in nautobot dex; do
  kubeseal \
    --scope cluster-wide \
    --allow-empty-data \
    -o yaml \
    -f secret-nautobot-sso-$ns.yaml \
    -w components/01-secrets/encrypted-nautobot-sso-$ns.yaml
done

for ns in argo argo-events argocd dex; do
  kubeseal \
    --scope cluster-wide \
    --allow-empty-data \
    -o yaml \
    -f secret-argo-sso-$ns.yaml \
    -w components/01-secrets/encrypted-argo-sso-$ns.yaml
done

cd components/01-secrets/
rm -f kustomization.yaml
kustomize create --autodetect
cd ../..
