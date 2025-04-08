# OpenStack RabbitMQ Queue Dump Tool

You can use the `queue_dump.py` tool to inspect the OpenStack RabbitMQ notifications by displaying the messages and re-queueing them.

You can also use it to completely drain a rabbitmq queue, destroying all messages.

# Pre-requisites

1. Create a python virtual environment and install pika: `pip install -r requirements.txt`

2. Grab the rabbitmq credentials from kubernetes:

```
export RABBIT_USER=$(kubectl -n openstack get secret rabbitmq-default-user -o jsonpath="{.data.username}" | base64 --decode)
export RABBIT_PASS=$(kubectl -n openstack get secret rabbitmq-default-user -o jsonpath="{.data.password}" | base64 --decode)
```

3. Open a port to the rabbitmq server:

``` text
kubectl -n openstack port-forward svc/rabbitmq 5672
```

4. Use RabbitMq management UI to know more about Virtualhosts, Exchanges, Queues etc, follow the instructions [provided here](https://rackerlabs.github.io/understack/operator-guide/rabbitmq/):


5. Run the `queue_dump.py` tool:

``` text
 python queue_dump.py -h
usage: queue-dump [-h] -u USERNAME -p PASSWORD [--host HOST] [--port PORT] [--virtualhost VIRTUALHOST] [--queue QUEUE] [-v] [--destroy]

dump, print, list-events, and requeue an openstack notifications rabbitmq queue

options:
  -h, --help            show this help message and exit
  -u USERNAME, --username USERNAME
                        RabbitMQ username
  -p PASSWORD, --password PASSWORD
                        RabbitMQ password
  --host HOST           RabbitMQ hostname
  --port PORT           RabbitMQ port
  --virtualhost VIRTUALHOST
                        RabbitMQ virtual host
  --queue QUEUE         RabbitMQ queue
  -v, --verbose         Increase output verbosity
  --destroy             Warning: Destroys all messages!
```

# Example Usage

## Inspect a queue by displaying and re-queue all messages

```
python queue_dump.py -u $RABBIT_USER -p $RABBIT_PASS
```

## List OpenStack notifications event types

If you want to understand what are the different event-types being emitted by OpenStack notifications system, you can use:

```
python queue_dump.py --virtualhost $VIRTUAL_HOST -u $RABBIT_USER -p $RABBIT_PASS --queue notifications.info --list-event-types
```

## Find OpenStack notifications for a specific event type

If you need to find a specific event type to troubleshoot something, you can use:

```
python queue_dump.py -u $RABBIT_USER -p $RABBIT_PASS --event-type baremetal.node.power_set.start
```

## Find OpenStack Ironic notifications for a specific provision state

I needed to find the notification payload for OpenStack Ironic `clean failed` events:

```
python queue_dump.py -u $RABBIT_USER -p $RABBIT_PASS --provision-state 'clean failed'
```

## Drain a queue and destroy all messages

*Warning: This is a destructive action!*

```
python queue_dump.py -u $RABBIT_USER -p $RABBIT_PASS --destroy
```
