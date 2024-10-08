# RabbitMQ Cheat Sheet

## Get Admin Username and Pasasword

```bash
# Username
kubectl -n openstack get secret rabbitmq-default-user -o jsonpath="{.data.username}" | base64 --decode
# Password
kubectl -n openstack get secret rabbitmq-default-user -o jsonpath="{.data.password}" | base64 --decode
```

## Opening the UI

```bash
kubectl -n openstack port-forward svc/rabbitmq 15672
```

Then open <http://localhost:15672/> in your web browser and log in using the credentials from above.

## CLI

### List exchanges

```bash
kubectl -n openstack exec -it rabbitmq-server-0 -c rabbitmq -- rabbitmqadmin list exchanges
```

### List vhosts

```bash
kubectl -n openstack exec -it rabbitmq-server-0 -c rabbitmq -- rabbitmqadmin list vhosts
```

### List queues

```bash
kubectl -n openstack exec -it rabbitmq-server-0 -c rabbitmq -- rabbitmqadmin list queues
```

More details:

```bash
kubectl -n openstack exec -it rabbitmq-server-0 -c rabbitmq -- rabbitmqadmin list queues vhost name node messages message_stats.publish_details.rate
```

### Listen to the messages

```bash
rabbitmqadmin --vhost=<VHOST> get queue=<QueueName> requeue=true
```

For example:

```bash
kubectl -n openstack exec -it rabbitmq-server-0 -c rabbitmq -- rabbitmqadmin --vhost=nova get queue=notifications.info ackmode=ack_requeue_true count=5
```

### Capture a queue to a file

```bash
kubectl -n openstack exec -it rabbitmq-server-0 -c rabbitmq -- rabbitmqadmin --vhost=nova get queue=notifications.info ackmode=ack_requeue_true payload_file=/tmp/test.json
kubectl -n openstack cp rabbitmq-server-0:/tmp/test.json -c rabbitmq /tmp/test.json
```
