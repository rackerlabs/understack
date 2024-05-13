# Kubernetes

You will need a kubernetes environment to deploy and use UnderStack. Good options for a
small kubernetes development environment are [k3s](https://docs.k3s.io/) and [kind](https://kind.sigs.k8s.io/).

## Kubernetes Tools

UnderStack also uses common kubernetes tools: Helm, Kustomize, and Kubeseal.

### Helm

[Helm](https://helm.sh) is a package manager for kubernetes and UnderStack uses a number of
upstream Helm charts.

Helm install on Ubuntu:

```bash
curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
sudo apt-get install apt-transport-https --yes
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo apt-get update
sudo apt-get install helm
```

### Kustomize

[Kustomize](https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/) helps make customizations in kubernetes easier.

Kustomize install on Ubuntu:

```bash
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh"  | bash
sudo mv kustomize /usr/bin
```

### Kubeseal

[Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) and the `kubeseal` cli tool make it possible to
store sescrets in a public repository.

Kubeseal install on Ubuntu:

```bash
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.26.0/kubeseal-0.26.0-linux-amd64.tar.gz
tar xzf kubeseal-0.26.0-linux-amd64.tar.gz
sudo mv kubeseal /usr/bin
```
