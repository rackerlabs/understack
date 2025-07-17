#!/bin/bash

wait_for_cert_manager() {
  local cmd="kubectl apply -f bootstrap/cert-manager/cmchecker.yaml --dry-run=server"
  max_tries=10
  current_retry=1

  echo -n "Waiting for cert-manager to become available."
  until $cmd &>/dev/null; do
    if (( current_retry == max_tries )); then
      echo "Timed out waiting for cert-manager to come up."
      exit 1
    else
      echo -n "."
    fi
    sleep 2
    (( current_retry++ ))
  done
  echo " done."
}

kubectl kustomize --enable-helm bootstrap/cert-manager/ | kubectl apply --server-side -f -
wait_for_cert_manager
kubectl kustomize --enable-helm bootstrap | kubectl apply --server-side -f -
kubectl apply -f bootstrap/cert-manager/issuer-kube-system-self-signed.yaml
export DEPLOY_NAME=selfsigned
export DNS_ZONE=local
cat bootstrap/argocd/ingress.yaml | envsubst | kubectl apply -f -
kubectl apply -f bootstrap/external-secretes/pwsafe.yaml
