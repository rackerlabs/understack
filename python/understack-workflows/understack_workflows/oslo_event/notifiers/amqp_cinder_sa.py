import json

import pika

from understack_workflows.main.openstack_oslo_event import HandlerResult


class StorageAutomationNotifier:
    def __init__(
        self, username, password, vhost, address, queue_name, exchange_name, port
    ) -> None:
        self.username = username
        self.password = password
        self.address = address
        self.vhost = vhost
        self.port = port
        self.queue_name = queue_name
        self.exchange_name = exchange_name

    def __del__(self):
        """Disconnect from AMQP broker."""
        self.connection.close()

    def publish(self, event, event_type: str, result: HandlerResult):
        if not self.connection:
            self._connect()

        message = {"result": result}
        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key="job.completed",
            body=json.dumps(message),
        )

    def _connect(self):
        credentials = pika.PlainCredentials(self.username, self.password)
        connection_params = pika.ConnectionParameters(
            host=self.address,
            port=self.port,
            virtual_host=self.vhost,
            credentials=credentials,
        )

        self.connection = pika.BlockingConnection(connection_params)
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.exchange_declare(self.exchange_name, exchange_type="fanout")
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name)
