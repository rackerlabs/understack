# kea-dhcp

![Version: 0.6.1](https://img.shields.io/badge/Version-0.6.1-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 2.1.2](https://img.shields.io/badge/AppVersion-2.1.2-informational?style=flat-square)

Helm chart for kea-dhcp

**This chart is not maintained by the upstream project and any issues with the chart should be raised [here](https://github.com/MGlants/charts/issues/new/choose)**
**More than 1 replicas is not supported by now**

## Requirements

## Dependencies

| Repository | Name | Version |
|------------|------|---------|

## TL;DR

```console
helm repo add mglants http://charts.glants.xyz
helm repo update
helm install kea-dhcp mglants/kea-dhcp
```

## Installing the Chart

To install the chart with the release name `kea-dhcp`

```console
helm install kea-dhcp mglants/kea-dhcp
```

## Uninstalling the Chart

To uninstall the `kea-dhcp` deployment

```console
helm uninstall kea-dhcp
```

The command removes all the Kubernetes components associated with the chart **including persistent volumes** and deletes the release.

## Configuration

Read through the [values.yaml](./values.yaml) file. It has several commented out suggested values.

Specify each parameter using the `--set key=value[,key=value]` argument to `helm install`.

```console
helm install kea-dhcp \
  --set env.TZ="America/New York" \
    mglants/kea-dhcp
```

Alternatively, a YAML file that specifies the values for the above parameters can be provided while installing the chart.

```console
helm install kea-dhcp mglants/kea-dhcp -f values.yaml
```

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` |  |
| clusterDomain | string | `"cluster.local"` |  |
| fullnameOverride | string | `""` |  |
| image.pullPolicy | string | `"IfNotPresent"` |  |
| image.repository | string | `"smailkoz/kea-dhcp"` |  |
| image.tag | string | `""` |  |
| imagePullSecrets | list | `[]` |  |
| kea.ctrlagent.enabled | bool | `false` |  |
| kea.ctrlagent.loglevel | string | `"DEBUG"` |  |
| kea.ddns.enabled | bool | `false` |  |
| kea.ddns.forward | object | `{}` |  |
| kea.ddns.loglevel | string | `"DEBUG"` |  |
| kea.ddns.prefix | string | `"myhost"` |  |
| kea.ddns.reverse | object | `{}` |  - name: home.arpa.   key-name: ''   dns-servers:   - ip-address: 172.16.32.2     port: 53 |
| kea.ddns.suffix | string | `"home.arpa."` |  |
| kea.dhcp4.enabled | bool | `true` |  |
| kea.dhcp4.loglevel | string | `"DEBUG"` |  |
| kea.dhcp4.options | object | `{}` |  |
| kea.dhcp4.rebindtimer | string | `"2000"` |  |
| kea.dhcp4.renewtimer | string | `"1000"` |  |
| kea.dhcp4.reservations | object | `{}` |    data: 192.168.1.2 - name: domain-name   data: local - name: domain-search   data: local - code: 66   data: 192.168.1.2   name: tftp-server-name |
| kea.dhcp4.subnets | object | `{}` |    hw-address: "aa:aa:aa:aa:aa:aa"   hostname: "hostname"   option-data:     - name: "tftp-servers"       data: "10.1.1.202,10.1.1.203" |
| kea.dhcp4.validlifetime | string | `"4000"` |  |
| kea.dhcp6.enabled | bool | `false` |  |
| kea.dhcp6.loglevel | string | `"DEBUG"` |  |
| kea.dhcp6.options | object | `{}` |  |
| kea.dhcp6.rebindtimer | string | `"2000"` |  |
| kea.dhcp6.renewtimer | string | `"1000"` |  |
| kea.dhcp6.reservations | object | `{}` |  |
| kea.dhcp6.subnets | object | `{}` |    duid: "aa:aa:aa:aa:aa:aa"   hostname: "hostname"   option-data:     - name: "dns-servers"       data: "2001:db8:2::45, 2001:db8:2::100" |
| kea.dhcp6.validlifetime | string | `"4000"` |  |
| livenessProbe.enabled | bool | `true` |  |
| metrics.enabled | bool | `false` |  |
| metrics.service.annotations | object | `{"prometheus.io/port":"9547","prometheus.io/scrape":"true"}` |  loadBalancerIP: |
| metrics.service.labels | object | `{}` |  |
| metrics.service.type | string | `"ClusterIP"` |  |
| nameOverride | string | `""` |  |
| nodeSelector | object | `{}` |  |
| persistence.enabled | bool | `false` |  |
| persistence.size | string | `"100Mi"` |  |
| podAnnotations | object | `{}` |  |
| podSecurityContext | object | `{}` |  |
| readinessProbe.enabled | bool | `true` |  |
| replicaCount | int | `1` |  |
| resources.limits.cpu | string | `"200m"` |  |
| resources.limits.memory | string | `"256Mi"` |  |
| resources.requests.cpu | string | `"100m"` |  |
| resources.requests.memory | string | `"128Mi"` |  |
| role.annotations | object | `{}` |  |
| roleBinding.annotations | object | `{}` |  |
| securityContext | object | `{}` |  |
| service.ctrl.annotations | object | `{}` |  nodePort: |
| service.ctrl.loadBalancerIP | string | `nil` |  |
| service.ctrl.port | int | `8000` |  |
| service.ctrl.type | string | `"ClusterIP"` |  |
| service.dhcp.annotations | object | `{}` |  nodePort: |
| service.dhcp.loadBalancerIP | string | `nil` |  |
| service.dhcp.port | int | `67` |  |
| service.dhcp.type | string | `"ClusterIP"` |  |
| serviceAccount.annotations | object | `{}` |  |
| serviceAccount.name | string | `""` |  If not set and create is true, a name is generated using the fullname template |
| sidecar.image.pullPolicy | string | `"IfNotPresent"` |  |
| sidecar.image.repository | string | `"smailkoz/kea-dhcp-sidecar"` |  |
| sidecar.image.tag | string | `""` |  |
| sidecar.resources.limits.cpu | string | `"50m"` |  |
| sidecar.resources.limits.memory | string | `"128Mi"` |  |
| sidecar.resources.requests.cpu | string | `"10m"` |  |
| sidecar.resources.requests.memory | string | `"32Mi"` |  |
| tolerations | list | `[]` |  |

## Changelog

### Version 0.6.1

#### Added

N/A

#### Changed

N/A

#### Fixed

* probes values fixed

### Older versions

A historical overview of changes can be found on [ArtifactHUB](https://artifacthub.io/packages/helm/mglants/kea-dhcp?modal=changelog)

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v0.1.1](https://github.com/k8s-at-home/helm-docs/releases/v0.1.1)
