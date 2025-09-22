#!/bin/bash

set -ex

thisdir=$(dirname "$0")

argocd_repo=$(cat "${thisdir}/../apps/appsets/argocd/appset-argocd.yaml" | yq -r '.spec.template.spec.sources[0].repoURL')
argocd_rev=$(cat "${thisdir}/../apps/appsets/argocd/appset-argocd.yaml" | yq -r '.spec.template.spec.sources[0].targetRevision')

helm repo add argo "${argocd_repo}"
helm repo update argo

helm template argo-cd argo-cd \
  --version "${argocd_rev}" \
  --create-namespace \
  -f "${thisdir}/../components/argocd/values.yaml" \
  | kubectl -n argocd apply -f -
