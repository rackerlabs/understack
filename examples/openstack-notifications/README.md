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

3. Run the `queue_dump.py` tool:

``` text
 python queue_dump.py -h
usage: queue-dump [-h] -u USERNAME -p PASSWORD [--host HOST] [--port PORT] [--virtualhost VIRTUALHOST] [--queue QUEUE] [-v] [--destroy]

dump, print, and requeue an openstack notifications rabbitmq queue

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

## Drain a queueu and destroy all messages

*Warning: This is a destructive action!*

```
python queue_dump.py -u $RABBIT_USER -p $RABBIT_PASS --destroy
```
