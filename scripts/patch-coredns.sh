#!/bin/bash
set -e
EXISTING_COREFILE=$(kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}')

ADD_LINE="    rewrite name dexidp.local ingress-nginx-controller.ingress-nginx.svc.cluster.local"

if grep -q "$ADD_LINE" <(echo "$EXISTING_COREFILE"); then
  echo "Configmap already patched."
  exit 0
fi
# shellcheck disable=SC2001
PATCHED_COREFILE=$(echo "$EXISTING_COREFILE" | sed -e "s/^}$/${ADD_LINE}\n\}/")


echo "[*] Patching coredns ConfigMap"
kubectl -n kube-system --dry-run=client create cm coredns  \
  --from-literal=Corefile="$PATCHED_COREFILE" -o yaml \
  | kubectl -n kube-system replace -f -

echo "[*] Restarting CoreDNS"
kubectl -n kube-system rollout restart deployment coredns
