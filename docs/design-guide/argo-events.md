# Argo Events

The UnderStack project utilizes [Argo Events][argo-events] to provide
uniform event-driven automation. Operations can be provided within
UnderStack or defined by users to provide additional operations on
events.

Some examples of how UnderStack utilizes Argo Events are:

* Listen to OpenStack notifications via RabbitMQ message queues
* Propagate updates to Nautobot for inventory synchronization
* Trigger asynchronous operations that are outside the scope of OpenStack plugins
* Maintain loose coupling between OpenStack and external automation workflows

## Architecture & Security Model

[Argo Events][argo-events] operates within the namespace (argo-events),
while the actual [EventSources][argo-events-eventsource] and [Sensors][argo-events-sensor]
run in other namespaces on the cluster.

### Argo Events Configuration

We install the controller and the validating webhook into the (argo-events)
namespace.

## EventSource and Sensor Configuration

[Sensors][argo-events-sensor] must be co-located with the [EventSource][argo-events-eventsource]
they are using so you will find them in multiple namespaces.

### Proper Definitions

You must configure the `dependencies` section of your [Sensor][argo-events-sensor]
correctly for it to properly trigger on events. For example below is
a partial snippet of an [argo-events-eventsource] named `openstack-neutron`
which provides one event named `notifications`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: EventSource
metadata:
  name: openstack-neutron  # THIS IS YOUR eventSourceName
spec:
  amqp:
    notifications:  # THIS IS YOUR eventName
      url: amqp://localhost
      routingKey: key
```

Your [Sensor][argo-events-sensor] would need to be defined as follows:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Sensor
metadata:
  name: my-sensor
spec:
  dependencies:
  - eventName: notifications  # MUST MATCH ABOVE
    eventSourceName: openstack-neutron  # MUST MATCH ABOVE
    name: your-choice
```

### Service Accounts

[ServiceAccount][argo-events-sensor-sa]s need to be specifically
configured for the [Sensor][argo-events-sensor] to be able to execute
the operation that you would like to happen in response to the event. These
service accounts should be created with the minimal permissions necessary
for the sensor and to then execute the operation. For example, many of our
existing [Sensor][argo-events-sensor]s execute [Argo Workflow](./argo-workflows.md)s
in response to a trigger so they only need to be able to create the workflow
from the workflowtemplate.

[argo-events]: <https://argoproj.github.io/argo-events/>
[argo-events-sensor]: <https://argoproj.github.io/argo-events/concepts/sensor/>
[argo-events-eventsource]: <https://argoproj.github.io/argo-events/concepts/event_source/>
[argo-events-sensor-sa]: <https://argoproj.github.io/argo-events/service-accounts/#service-account-for-sensors>
