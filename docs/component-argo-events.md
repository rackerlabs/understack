# Argo Events

[Argo Events][argo-events] is a Kubernetes-native event-driven automation framework. We can use Argo Events to trigger
autmoations processes from any of the internal Understack (and potentially external) components. Currently we leverage a
few of the Argo Events components:

## EventSource

These define which sources we will consume events from, transform them into cloudevents, and then ship them over the
eventbus. For example by default, Understack is listening for Nautobot Webhook EventSources at:

`nautobot-webhook-eventsource-svc.argo-events.svc.cluster.local:12000/nautobot`

## Sensor

These define the inputs we're listening for on the eventbus, and then responds by executing triggers. For example we
can trigger Argo Workflow submissions on cloudevents created by webhooks sent to the above mentioned EventSource.

[argo-events]: <https://argoproj.github.io/argo-events/>
