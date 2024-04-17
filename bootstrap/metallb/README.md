# MetalLB

We can use metallb with a couple unused IP addresses to provide
the Kubernetes LoadBalancer service type.

## Install MetalLB

```bash
cd components/20-metallb/
kubectl kustomize . | kubectl create -f -
```

## Edit and apply metallb config with our IP addresses

Things to change:
* IPAddressPool list of IPs
* L2Advertisement network interface name

```bash
vim example-create-metallb.yaml
kubectl apply -f example-create-metallb.yaml
```

## Simple test application to test if it's working

```bash
kubectl apply -f example-app-with-lb.yaml
```
