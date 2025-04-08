import pika
import json
import argparse


parser = argparse.ArgumentParser(
    prog="queue-dump",
    description="dump, print, and requeue an openstack notifications rabbitmq queue",
)
parser.add_argument(
    "-u", "--username", type=str, required=True, help="RabbitMQ username"
)
parser.add_argument(
    "-p", "--password", type=str, required=True, help="RabbitMQ password"
)
parser.add_argument("--host", type=str, default="localhost", help="RabbitMQ hostname")
parser.add_argument("--port", type=int, default=5672, help="RabbitMQ port")
parser.add_argument(
    "--virtualhost", type=str, default="ironic", help="RabbitMQ virtual host"
)
parser.add_argument(
    "--queue",
    type=str,
    default="ironic_versioned_notifications.info",
    help="RabbitMQ queue",
)
parser.add_argument(
    "--event-type",
    type=str,
    required=False,
    help="Scan for a specific OpenStack notification event type",
)
parser.add_argument(
    "--list-event-types",
    action="store_true",
    help="List event_type values found in the queue",
)
parser.add_argument(
    "--provision-state",
    type=str,
    required=False,
    help="Scan for a specific OpenStack Ironic provision state",
)
parser.add_argument(
    "-v", "--verbose", action="store_true", help="Increase output verbosity"
)
parser.add_argument(
    "--destroy", action="store_true", help="Warning: Destroys all messages!"
)
args = parser.parse_args()


print(
    f"Connecting to: host: {args.host} port: {args.port} virtual host: {args.virtualhost} queue: {args.queue}"
)

# Set up the RabbitMQ connection parameters
credentials = pika.PlainCredentials(args.username, args.password)
parameters = pika.ConnectionParameters(
    host=args.host,
    port=args.port,
    virtual_host=args.virtualhost,
    credentials=credentials,
)

# Establish a connection to RabbitMQ
connection = pika.BlockingConnection(parameters)
channel = connection.channel()


# Function to handle messages, printing and requeuing them
def callback(ch, method, properties, body):
    if args.verbose:
        print(f"Received message: {body}")

    parsed = json.loads(body)
    message = json.loads(parsed.get("oslo.message", {}))
    if message:
        parsed["oslo.message"] = message

    event_type = message.get("event_type")

    if args.list_event_types and message.get("event_type", None):
        print(event_type)
    else:
        if args.event_type or args.provision_state:
            if args.event_type:
                event_type = message.get("event_type")
                if event_type == args.event_type:
                    print(json.dumps(parsed, indent=4))

            if args.provision_state:
                payload = message.get("payload", {})
                ironic_object = payload.get("ironic_object.data", {})
                provision_state = ironic_object.get("provision_state")
                if provision_state == args.provision_state:
                    print(json.dumps(parsed, indent=4))
        else:
            print(json.dumps(parsed, indent=4))

        if args.destroy:
            print("Destroying message.")
            # Acknowledge that the message has been handled, removing it from the queue.
            ch.basic_ack(delivery_tag=method.delivery_tag)

        else:
            if args.verbose:
                print("Re-queueing the message.")

            # Requeue the message using using nack
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


# Set up the consumer to pull messages from the queue
channel.basic_consume(queue=args.queue, on_message_callback=callback)

print(f"Waiting for messages in queue '{args.queue}'. To exit press CTRL+C")
try:
    # Start consuming messages
    channel.start_consuming()

except KeyboardInterrupt:
    # Gracefully stop the consumer on CTRL+C
    print("\nStopping consumer.")
    channel.stop_consuming()

# Close the connection
connection.close()
