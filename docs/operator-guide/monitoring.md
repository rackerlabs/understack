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

## Alerts

### rabbitmq-node-low-disk

OpenStack services use RabbitMQ as a message bus. But if there are no consumers to read the messages,
the RabbitMQ queues can grow indefinitely and will eventually fill the pod disk and crash the
RabbitMQ server.

We set a default message TTL to automatically purge old messages. Here is an example:
<https://github.com/rackerlabs/understack/blob/main/components/nova/nova-rabbitmq-queue.yaml#L46-L61>

However if you add new services or create new queues, the TTLs may not exist, so we have this alert
as an extra precaution.

You can check the queue sizes by logging in to the RabbitMQ web admin, viewing the the `Queues and Streams` tab,
and then sorting by the total number of messages in the queue.

See the [RabbitMQ Operator Guide](./rabbitmq.md) for more information and troubleshooting commands, including
how to purge a queue.
