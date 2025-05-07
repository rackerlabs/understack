# dexop

Kubernetes operator to manage [DEX][dex] Oauth2 clients.

[dex]: <https://dexidp.io/>

The `dexop` operator is designed to simplify the management of OAuth2 clients
in Dex, a popular open-source identity and authentication service. By
leveraging Kubernetes resources, `dexop` allows for more streamlined control
over client lifecycles.

## Supported Operations

The following operations are supported by the `dexop` operator:

- **Client Management**: Create, update, and delete `Client`s in Dex.
- **Password Management**: Update passwords for existing clients, or
  automatically generate and store random passwords as Kubernetes secrets.
- **Secret Integration**: Read passwords from pre-existing `Secret`s and
  synchronize them with Dex.
- **Redirect URI Updates**: Update `redirectURIs` for existing `Client`s,
ensuring flexibility in handling client redirects.

## Example Usage

### Generate password

```yaml
---
apiVersion: dex.rax.io/v1alpha1
kind: Client
metadata:
  name: bob-client
spec:
  name: bob
  secretName: bobs-secret
  generateSecret: true
  redirectURIs:
    - http://localhost:8080
    - https://some.service.example.com/
```

The snippet above will contact configured Dex instance over GRPC API, create an
Oauth2 client named `bob`. The created client will have a randomly generated
password. The value of the password will be stored as a `Secret` and can be
read by any application running in the same Kubernetes namespace, providing it
has appropriate permissions.

### Pre-existing Secret

Sometimes, we may want to explicitly set the password or simply control it
externally. This can be done by creating the Secret and providing its name.

```yaml
---
apiVersion: dex.rax.io/v1alpha1
kind: Client
metadata:
  name: fred-client
spec:
  name: fred
  secretName: my-secret
  generateSecret: false  # defaults to false
  redirectURIs:
    - https://freds.website.com/oauth2/callback
```

### Secrets in different namespace

By default, the `dexop` assumes that Secrets will be placed in the same
namespace as the `Client` resource. However, in some of the setups it is
required to use different namespace. This can be configured with
`secretNamespace` attribute.

```yaml
apiVersion: dex.rax.io/v1alpha1
kind: Client
metadata:
  labels:
  name: keystone-client
spec:
  name: keystone
  secretName: keystone-secret
  secretNamespace: openstack
  generateSecret: true
  redirectURIs:
    - http://localhost:8080
    - https://keystone.openstack.svc.cluster.local/web/oauth2/callback
```

## Installation

This operator is distributed through a Helm chart located in the
`go/dexop/helm` directory.

- Adjust
  [values.yaml](https://github.com/rackerlabs/understack/tree/main/go/dexop/helm/values.yaml)
for your needs.
- Create a Secret with credentials for `dexop` to access the `DEX` API. Example setup:

```yaml
---
apiVersion: v1
kind: Secret
metadata:
  name: dexop-dex-client
type: kubernetes.io/tls
data:
  tls.crt: LS0tLS1CRUdJTiBDRVJUSUZJQ0....
  tls.key: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tC....
  ca.pem: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tL....
```

If deploying without helm, the container image is available [here](https://github.com/rackerlabs/understack/pkgs/container/understack%2Fdexop).

## Development

### Prerequisites

- go version v1.23.0+
- docker version 17.03+.
- kubectl version v1.11.3+.
- Access to a Kubernetes v1.11.3+ cluster.

Make sure that your kubectl is not connected to a production cluster, ideally
use a local cluster like [kind](https://kind.sigs.k8s.io/).

### To Deploy on the cluster

**Build and push your image to the location specified by `IMG`:**

```sh
make docker-build docker-push IMG=<some-registry>/dexop:tag
```

**NOTE:** This image ought to be published in the personal registry you
specified. And it is required to have access to pull the image from the working
environment. Make sure you have the proper permission to the registry if the
above commands don’t work.

**Install the CRDs into the cluster:**

```sh
make install
```

**Deploy the Manager to the cluster with the image specified by `IMG`:**

```sh
make deploy IMG=<some-registry>/dexop:tag
```

> **NOTE**: If you encounter RBAC errors, you may need to grant yourself cluster-admin
privileges or be logged in as admin.

**Create instances of your solution**
You can apply the samples (examples) from the config/sample:

```sh
kubectl apply -k config/samples/
```

>**NOTE**: Ensure that the samples has default values to test it out.

### To Uninstall

**Delete the instances (CRs) from the cluster:**

```sh
kubectl delete -k config/samples/
```

**Delete the APIs(CRDs) from the cluster:**

```sh
make uninstall
```

**UnDeploy the controller from the cluster:**

```sh
make undeploy
```

## Project Distribution

Following are the steps to build the installer and distribute this project to users.

1. Build the installer for the image built and published in the registry:

```sh
make build-installer IMG=<some-registry>/dexop:tag
```

NOTE: The makefile target mentioned above generates an 'install.yaml'
file in the dist directory. This file contains all the resources built
with Kustomize, which are necessary to install this project without
its dependencies.

1. Using the installer

Users can just run `kubectl apply -f <URL for YAML BUNDLE>` to install the
project, i.e.:

```sh
kubectl apply -f https://raw.githubusercontent.com/<org>/dexop/<tag or branch>/dist/install.yaml
```

The project can be installed through Helm as well (described in the Install section)

## Contributing

**NOTE:** Run `make help` for more information on all potential `make` targets

More information can be found via the [Kubebuilder Documentation](https://book.kubebuilder.io/introduction.html)

## License

Copyright 2025 Rackspace Technology.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
