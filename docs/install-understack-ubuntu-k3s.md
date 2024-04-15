# Installing UnderStack on Ubuntu 22.04 + K3s

## Get UnderStack

First, let's git clone the understack repo:

```bash
git clone https://github.com/rackerlabs/understack.git
```

## Install Pre-requisites

Install some packages we'll need later and some useful troubleshooting utilities.

```bash
apt-get -y install curl jq net-tools telnet git apt-transport-https wget
```

## Update Ubuntu

Update to the latest ubuntu packages and reboot if necessary.

```bash
apt-get -y update
```

## Install K3s

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable=traefik" sh -
```

References:

* [https://docs.k3s.io/](https://docs.k3s.io/)

## Install Helm

The K3s installer will install kubectl, but we'll also need helm for the UnderStack install.

```bash
curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
sudo apt-get install apt-transport-https --yes
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo apt-get update
sudo apt-get install helm
```

References:

* [https://helm.sh/docs/intro/install/](https://helm.sh/docs/intro/install/)

## Install Kustomize

```bash
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh"  | bash
sudo mv kustomize /usr/bin
```

References:

* [https://kubectl.docs.kubernetes.io/installation/kustomize/](https://kubectl.docs.kubernetes.io/installation/kustomize/)

## Install Kubeseal

```bash
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.26.0/kubeseal-0.26.0-linux-amd64.tar.gz
tar xzf kubeseal-0.26.0-linux-amd64.tar.gz
sudo mv kubeseal /usr/bin
```

References:

* [https://github.com/bitnami-labs/sealed-secrets?tab=readme-ov-file#installation](https://github.com/bitnami-labs/sealed-secrets?tab=readme-ov-file#installation)

## Test Kubernetes

K3s installer should give us a working kubernetes.

The kubectl config from k3s is in `/etc/rancher/k3s/k3s.yaml` and kubectl will automatically use it.

See everything running in the new k3s kubernetes cluster:

```bash
kubectl get all --all-namespaces
```

## Install UnderStack

Get the repo:

```bash
git clone https://github.com/rackerlabs/understack.git
```

References:

* [https://github.com/rackerlabs/understack](https://github.com/rackerlabs/understack)

### Bootstrap UnderStack

Run the initial bootstrap:

```bash
./bootstrap/bootstrap.sh
```

Wait a couple minutes for it to finish bootstrapping. Then:

```bash
kubectl -n argocd apply -k apps/operators/
```

Generate secrets:

```bash
# (optional) copy rancher kubectl config to ~/.kube/config
# cp /etc/rancher/k3s/k3s.yaml /root/.kube/config && chmod go-rwx /root/.kube/config

# generate secrets
./scripts/easy-secrets-gen.sh

# make the namespaces where the secrets will live
kubectl create ns openstack
kubectl create ns nautobot

# load the secrets
kubectl apply -k components/01-secrets/
```

```bash
kubectl -n argocd apply -k apps/components/
```

### Bootstrap: Phase 1 Complete

After a couple minutes, the initial UnderStack bootstrap phase will complete,
and your cluster should look similar to the output below.

Notice we have the following components available:

* mariadb
* postgres
* rabbitmq
* argo workflows
* argo cd
* ingress-nginx
* nautobot
* cert-manager

```bash
# kubectl get all  --all-namespaces
NAMESPACE           NAME                                                    READY   STATUS      RESTARTS        AGE
kube-system         pod/local-path-provisioner-84db5d44d9-ft4s5             1/1     Running     0               169m
kube-system         pod/coredns-6799fbcd5-4swtb                             1/1     Running     0               169m
kube-system         pod/svclb-traefik-986d0605-wvkcp                        2/2     Running     0               169m
kube-system         pod/helm-install-traefik-crd-zfbpj                      0/1     Completed   0               169m
kube-system         pod/helm-install-traefik-4ngnx                          0/1     Completed   1               169m
kube-system         pod/traefik-f4564c4f4-mlqbz                             1/1     Running     0               169m
kube-system         pod/metrics-server-67c658944b-22r2s                     1/1     Running     0               169m
kube-system         pod/svclb-ingress-nginx-controller-169e70b9-b769n       0/2     Pending     0               81m
argocd              pod/argo-cd-argocd-redis-58779b9ddf-vxd82               1/1     Running     0               81m
ingress-nginx       pod/ingress-nginx-admission-create-zpxr7                0/1     Completed   0               81m
ingress-nginx       pod/ingress-nginx-admission-patch-xxbhl                 0/1     Completed   1               81m
kube-system         pod/sealed-secrets-controller-58bfb4d565-vwlrz          1/1     Running     0               81m
argocd              pod/argo-cd-argocd-repo-server-889b6979c-7vgbv          1/1     Running     0               81m
argocd              pod/argo-cd-argocd-server-7c665bdb99-7jrk2              1/1     Running     0               81m
argocd              pod/argo-cd-argocd-application-controller-0             1/1     Running     0               81m
ingress-nginx       pod/ingress-nginx-controller-6858749594-svlmt           1/1     Running     0               81m
cert-manager        pod/cert-manager-5c9d8879fd-msnhr                       1/1     Running     0               32m
cert-manager        pod/cert-manager-cainjector-6cc9b5f678-ksnz7            1/1     Running     0               32m
cert-manager        pod/cert-manager-webhook-7bb7b75848-mw7xl               1/1     Running     0               32m
rabbitmq-system     pod/rabbitmq-cluster-operator-ccf488f4c-8jntf           1/1     Running     0               13m
rabbitmq-system     pod/messaging-topology-operator-85486d7848-ss9wv        1/1     Running     0               13m
postgres-operator   pod/pgo-6d794c46cf-nddkq                                1/1     Running     0               13m
mariadb-operator    pod/mariadb-operator-5644c8d7df-w4wj9                   1/1     Running     0               13m
mariadb-operator    pod/mariadb-operator-webhook-74f4b57d9d-z5hz7           1/1     Running     0               13m
mariadb-operator    pod/mariadb-operator-cert-controller-6586cb7db6-dfhlt   1/1     Running     0               13m
argo                pod/workflow-controller-954b4d959-vr2fg                 1/1     Running     0               9m9s
argo-events         pod/events-webhook-984788f96-rqmzm                      1/1     Running     0               9m9s
argo-events         pod/controller-manager-5d97d79554-sn6tf                 1/1     Running     0               9m9s
nautobot            pod/nautobot-repo-host-0                                2/2     Running     0               9m9s
argo                pod/argo-server-5df77fdc67-mzm8p                        1/1     Running     0               9m9s
openstack           pod/memcached-56458c6c9c-k855d                          2/2     Running     0               8m55s
openstack           pod/mariadb-0                                           1/1     Running     0               9m10s
nautobot            pod/nautobot-redis-master-0                             1/1     Running     0               8m55s
nautobot            pod/nautobot-celery-default-545d857c5-4lqsl             1/1     Running     2 (8m35s ago)   9m10s
openstack           pod/rabbitmq-server-0                                   1/1     Running     0               9m9s
nautobot            pod/nautobot-backup-sg6f-fq2m8                          0/1     Completed   0               8m45s
nautobot            pod/nautobot-default-844d45bf7-pthnd                    1/1     Running     0               9m10s
nautobot            pod/nautobot-default-844d45bf7-8blht                    1/1     Running     0               9m10s
nautobot            pod/nautobot-celery-beat-7764fb8b6c-vwhkp               1/1     Running     5 (6m43s ago)   9m10s
nautobot            pod/nautobot-instance1-v8mc-0                           4/4     Running     0               9m9s

NAMESPACE          NAME                                         TYPE           CLUSTER-IP      EXTERNAL-IP     PORT(S)                        AGE
default            service/kubernetes                           ClusterIP      10.43.0.1       <none>          443/TCP                        170m
kube-system        service/kube-dns                             ClusterIP      10.43.0.10      <none>          53/UDP,53/TCP,9153/TCP         169m
kube-system        service/metrics-server                       ClusterIP      10.43.140.224   <none>          443/TCP                        169m
kube-system        service/traefik                              LoadBalancer   10.43.240.66    172.27.232.20   80:31301/TCP,443:31743/TCP     169m
argocd             service/argo-cd-argocd-redis                 ClusterIP      10.43.50.168    <none>          6379/TCP                       81m
argocd             service/argo-cd-argocd-repo-server           ClusterIP      10.43.55.16     <none>          8081/TCP                       81m
argocd             service/argo-cd-argocd-server                ClusterIP      10.43.136.60    <none>          80/TCP,443/TCP                 81m
ingress-nginx      service/ingress-nginx-controller             LoadBalancer   10.43.247.18    <pending>       80:31390/TCP,443:31335/TCP     81m
ingress-nginx      service/ingress-nginx-controller-admission   ClusterIP      10.43.138.89    <none>          443/TCP                        81m
kube-system        service/sealed-secrets-controller            ClusterIP      10.43.205.142   <none>          8080/TCP                       81m
kube-system        service/sealed-secrets-controller-metrics    ClusterIP      10.43.51.95     <none>          8081/TCP                       81m
cert-manager       service/cert-manager                         ClusterIP      10.43.206.85    <none>          9402/TCP                       32m
cert-manager       service/cert-manager-webhook                 ClusterIP      10.43.155.21    <none>          443/TCP                        32m
rabbitmq-system    service/webhook-service                      ClusterIP      10.43.94.7      <none>          443/TCP                        13m
mariadb-operator   service/mariadb-operator-webhook             ClusterIP      10.43.145.93    <none>          443/TCP                        13m
nautobot           service/nautobot-pods                        ClusterIP      None            <none>          <none>                         9m10s
openstack          service/rabbitmq-nodes                       ClusterIP      None            <none>          4369/TCP,25672/TCP             9m10s
openstack          service/mariadb-internal                     ClusterIP      None            <none>          3306/TCP                       9m10s
openstack          service/rabbitmq                             ClusterIP      10.43.212.13    <none>          15672/TCP,15692/TCP,5672/TCP   9m10s
openstack          service/mariadb                              ClusterIP      10.43.138.242   <none>          3306/TCP                       9m10s
nautobot           service/nautobot-default                     ClusterIP      10.43.76.64     <none>          443/TCP,80/TCP                 9m10s
nautobot           service/nautobot-ha                          ClusterIP      10.43.107.193   <none>          5432/TCP                       9m10s
nautobot           service/nautobot-primary                     ClusterIP      None            <none>          5432/TCP                       9m10s
nautobot           service/nautobot-replicas                    ClusterIP      10.43.154.155   <none>          5432/TCP                       9m9s
nautobot           service/nautobot-ha-config                   ClusterIP      None            <none>          <none>                         9m9s
argo               service/argo-server                          ClusterIP      10.43.20.228    <none>          2746/TCP                       9m9s
argo-events        service/events-webhook                       ClusterIP      10.43.41.70     <none>          443/TCP                        9m9s
openstack          service/memcached-metrics                    ClusterIP      10.43.95.160    <none>          9150/TCP                       8m55s
openstack          service/memcached                            ClusterIP      10.43.122.133   <none>          11211/TCP                      8m55s
nautobot           service/nautobot-redis-headless              ClusterIP      None            <none>          6379/TCP                       8m55s
nautobot           service/nautobot-redis-master                ClusterIP      10.43.196.127   <none>          6379/TCP                       8m55s

NAMESPACE     NAME                                                     DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
kube-system   daemonset.apps/svclb-traefik-986d0605                    1         1         1       1            1           <none>          169m
kube-system   daemonset.apps/svclb-ingress-nginx-controller-169e70b9   1         1         0       1            0           <none>          81m

NAMESPACE           NAME                                               READY   UP-TO-DATE   AVAILABLE   AGE
kube-system         deployment.apps/local-path-provisioner             1/1     1            1           169m
kube-system         deployment.apps/coredns                            1/1     1            1           169m
kube-system         deployment.apps/traefik                            1/1     1            1           169m
kube-system         deployment.apps/metrics-server                     1/1     1            1           169m
argocd              deployment.apps/argo-cd-argocd-redis               1/1     1            1           81m
argocd              deployment.apps/argo-cd-argocd-repo-server         1/1     1            1           81m
argocd              deployment.apps/argo-cd-argocd-server              1/1     1            1           81m
ingress-nginx       deployment.apps/ingress-nginx-controller           1/1     1            1           81m
cert-manager        deployment.apps/cert-manager                       1/1     1            1           32m
cert-manager        deployment.apps/cert-manager-cainjector            1/1     1            1           32m
cert-manager        deployment.apps/cert-manager-webhook               1/1     1            1           32m
kube-system         deployment.apps/sealed-secrets-controller          1/1     1            1           81m
rabbitmq-system     deployment.apps/rabbitmq-cluster-operator          1/1     1            1           13m
rabbitmq-system     deployment.apps/messaging-topology-operator        1/1     1            1           13m
postgres-operator   deployment.apps/pgo                                1/1     1            1           13m
mariadb-operator    deployment.apps/mariadb-operator                   1/1     1            1           13m
mariadb-operator    deployment.apps/mariadb-operator-webhook           1/1     1            1           13m
mariadb-operator    deployment.apps/mariadb-operator-cert-controller   1/1     1            1           13m
argo                deployment.apps/workflow-controller                1/1     1            1           9m9s
argo-events         deployment.apps/events-webhook                     1/1     1            1           9m9s
argo-events         deployment.apps/controller-manager                 1/1     1            1           9m9s
argo                deployment.apps/argo-server                        1/1     1            1           9m9s
openstack           deployment.apps/memcached                          1/1     1            1           8m55s
nautobot            deployment.apps/nautobot-celery-default            1/1     1            1           9m10s
nautobot            deployment.apps/nautobot-default                   2/2     2            2           9m10s
nautobot            deployment.apps/nautobot-celery-beat               1/1     1            1           9m10s

NAMESPACE           NAME                                                          DESIRED   CURRENT   READY   AGE
kube-system         replicaset.apps/local-path-provisioner-84db5d44d9             1         1         1       169m
kube-system         replicaset.apps/coredns-6799fbcd5                             1         1         1       169m
kube-system         replicaset.apps/traefik-f4564c4f4                             1         1         1       169m
kube-system         replicaset.apps/metrics-server-67c658944b                     1         1         1       169m
argocd              replicaset.apps/argo-cd-argocd-redis-58779b9ddf               1         1         1       81m
kube-system         replicaset.apps/sealed-secrets-controller-58bfb4d565          1         1         1       81m
argocd              replicaset.apps/argo-cd-argocd-repo-server-889b6979c          1         1         1       81m
argocd              replicaset.apps/argo-cd-argocd-server-7c665bdb99              1         1         1       81m
ingress-nginx       replicaset.apps/ingress-nginx-controller-6858749594           1         1         1       81m
cert-manager        replicaset.apps/cert-manager-5c9d8879fd                       1         1         1       32m
cert-manager        replicaset.apps/cert-manager-cainjector-6cc9b5f678            1         1         1       32m
cert-manager        replicaset.apps/cert-manager-webhook-7bb7b75848               1         1         1       32m
rabbitmq-system     replicaset.apps/rabbitmq-cluster-operator-ccf488f4c           1         1         1       13m
rabbitmq-system     replicaset.apps/messaging-topology-operator-85486d7848        1         1         1       13m
postgres-operator   replicaset.apps/pgo-6d794c46cf                                1         1         1       13m
mariadb-operator    replicaset.apps/mariadb-operator-5644c8d7df                   1         1         1       13m
mariadb-operator    replicaset.apps/mariadb-operator-webhook-74f4b57d9d           1         1         1       13m
mariadb-operator    replicaset.apps/mariadb-operator-cert-controller-6586cb7db6   1         1         1       13m
argo                replicaset.apps/workflow-controller-954b4d959                 1         1         1       9m9s
argo-events         replicaset.apps/events-webhook-984788f96                      1         1         1       9m9s
argo-events         replicaset.apps/controller-manager-5d97d79554                 1         1         1       9m9s
argo                replicaset.apps/argo-server-5df77fdc67                        1         1         1       9m9s
openstack           replicaset.apps/memcached-56458c6c9c                          1         1         1       8m55s
nautobot            replicaset.apps/nautobot-celery-default-545d857c5             1         1         1       9m10s
nautobot            replicaset.apps/nautobot-default-844d45bf7                    2         2         2       9m10s
nautobot            replicaset.apps/nautobot-celery-beat-7764fb8b6c               1         1         1       9m10s

NAMESPACE   NAME                                                     READY   AGE
argocd      statefulset.apps/argo-cd-argocd-application-controller   1/1     81m
nautobot    statefulset.apps/nautobot-repo-host                      1/1     9m9s
nautobot    statefulset.apps/nautobot-instance1-v8mc                 1/1     9m9s
openstack   statefulset.apps/mariadb                                 1/1     9m10s
nautobot    statefulset.apps/nautobot-redis-master                   1/1     8m55s
openstack   statefulset.apps/rabbitmq-server                         1/1     9m9s

NAMESPACE       NAME                                       COMPLETIONS   DURATION   AGE
kube-system     job.batch/helm-install-traefik-crd         1/1           10s        169m
kube-system     job.batch/helm-install-traefik             1/1           13s        169m
ingress-nginx   job.batch/ingress-nginx-admission-create   1/1           6s         81m
ingress-nginx   job.batch/ingress-nginx-admission-patch    1/1           7s         81m
nautobot        job.batch/nautobot-backup-sg6f             1/1           2m48s      8m45s
```

## Install UnderStack Components

[https://github.com/rackerlabs/understack/blob/main/components/keystone/README.md](https://github.com/rackerlabs/understack/blob/main/components/keystone/README.md)

### OpenStack Pre-requisites

```bash
# clone the two repos because they reference the infra one as a relative path
# so you can't use real helm commands
git clone https://github.com/openstack/openstack-helm
git clone https://github.com/openstack/openstack-helm-infra
# update the dependencies cause we can't use real helm references
./scripts/openstack-helm-depend-sync.sh ironic
# keystone can now be used from a helm repo
helm repo add osh https://tarballs.opendev.org/openstack/openstack-helm/
```

Load the secrets values file from the cluster:

```bash
./scripts/gen-os-secrets.sh secret-openstack.yaml
```

Label the kubernetes nodes as being openstack enabled:

```bash
kubectl label node $(kubectl get nodes -o 'jsonpath={.items[*].metadata.name}') openstack-control-plane=enabled
```

### Keystone

Install keystone:

```bash
helm --namespace openstack install \
    keystone \
    osh/keystone \
    -f components/openstack-2023.1-jammy.yaml \
    -f components/keystone/aio-values.yaml \
    -f secret-openstack.yaml
```

Install the openstack admin client:

```bash
kubectl -n openstack apply -f https://raw.githubusercontent.com/rackerlabs/genestack/main/manifests/utils/utils-openstack-client-admin.yaml
```

Test if it's working:

```bash
kubectl exec -it openstack-admin-client -n openstack -- openstack catalog list
kubectl exec -it openstack-admin-client -n openstack -- openstack service list
```

References:

* [https://github.com/rackerlabs/understack/blob/main/components/keystone/README.md](https://github.com/rackerlabs/understack/blob/main/components/keystone/README.md)

### Ironic

First we need to update the `./components/ironic/aio-values.yaml` file and adjust a
setting to match our environment.

Change the network.pxe.device to be the network device on the physical host you'll
use for pxe network, for example a different network layout may use `eno2` for pxe.

```yaml
network:
  pxe:
    device: ens1f0
```

Install the OpenStack Ironic helm chart using our custom aio-values.yaml overrides:

```bash
helm --namespace openstack template \
    ironic \
    ./openstack-helm/ironic/ \
    -f components/ironic/aio-values.yaml \
    -f secret-openstack.yaml \
    | kubectl -n openstack apply -f -
```

Check if it's working:

```bash
kubectl exec -it openstack-admin-client -n openstack -- openstack baremetal driver list
kubectl exec -it openstack-admin-client -n openstack -- openstack baremetal conductor list
```

If everything is working, you should see output similar to the following:

```bash
# kubectl exec -it openstack-admin-client -n openstack -- openstack baremetal conductor list
+---------------------------------------------+-----------------+-------+
| Hostname                                    | Conductor Group | Alive |
+---------------------------------------------+-----------------+-------+
| 915966-utility01-ospcv2-iad.openstack.local |                 | True  |
+---------------------------------------------+-----------------+-------+
```

References:

* [https://github.com/rackerlabs/understack/blob/main/components/ironic/README.md](https://github.com/rackerlabs/understack/blob/main/components/ironic/README.md)
