#!/bin/sh

# install k3s, we'll use different cidrs for kubernetes,
# because we're using 10.0.0.0/8 already.
# https://docs.k3s.io/cli/server#networking
echo "Installing k3s..."
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable=traefik --cluster-cidr=172.20.0.0/16 --service-cidr=172.21.0.0/16" sh -

echo "Installing helm..."
curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
sudo apt-get install apt-transport-https --yes
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo apt-get update
sudo apt-get install helm

echo "Installing kustomize..."
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh"  | bash
sudo mv kustomize /usr/bin

echo "Installing kubeseal..."
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.26.0/kubeseal-0.26.0-linux-amd64.tar.gz
tar xzf kubeseal-0.26.0-linux-amd64.tar.gz
sudo mv kubeseal /usr/bin
