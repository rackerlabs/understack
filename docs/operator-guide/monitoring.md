# Monitoring Stack

UnderStack uses the `kube-prometheus-stack` which is a prometheus + grafana monitoring stack

<https://github.com/prometheus-operator/kube-prometheus>

It uses the namespace: `monitoring`

## Accessing Prometheus

Prometheus is not exposed publicly so a port-forward needs to be created
and then you'll be able to access the Prometheus UI.

``` bash
kubectl -n monitoring port-forward service/prometheus-operated 9090:9090
```

Once the port-forward is running, you can browse to <http://localhost:9090> to access Prometheus UI.

## Accessing AlertManager

AlertManager is not exposed publicly so a port-forward needs to be created
and then you'll be able to access the AlertManager UI.

``` bash
kubectl -n monitoring port-forward service/alertmanager-operated 9093:9093
```

Once the port-forward is running, you can browse to <http://localhost:9093> to access AlertManager UI.
