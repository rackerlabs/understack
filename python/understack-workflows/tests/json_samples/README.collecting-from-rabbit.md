The openstack event payloads published via Rabbitmq can be snooped on with commands like:

```sh
kubectl -n openstack exec -it rabbitmq-server-0 -c rabbitmq -- \
  rabbitmqadmin --vhost=neutron get \
    queue=notifications.info \
    ackmode=ack_requeue_true \
    count=1000 \
| awk -F\| '{print $5}' \
| fgrep network.create.end
```
