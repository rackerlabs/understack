# Understack Workflows

Understack Workflows is a collection of code, scripts, container definitions
centered around [Argo Workflows][argo-wf] to drive automated operations
based on events and other triggers in the system.

Due to the scoping of resources into different namespaces in the deployment
it is also split into multiple namespaces.

Specifics about each workflow can be seen in the Workflows
section.

## Kubernetes Resources

The resources here are grouped together by function.

**eventbus**
: [Argo Events][argo-events] uses an event bus to enqueue messages to process.

**eventsources**
: Defines how [Argo Events][argo-events] reads or receives messages to process.

**serviceaccounts**
: Kubernetes Service Accounts that workflows will run as.

**sensors**
: Defines messages of interest and what action to take on them. e.g. run a workflow.

**secrets**
: Defines secrets needed by sensors or workflows.

**workflowtemplates**
: Defines the workflows that are provided to be executed in the system.

### workflows/openstack

This is where Kubernetes manifests are stored for interacting with
resources in the `openstack` namespace.

The resources managed here are:

1. A RabbitMQ user named `argo` on the OpenStack RabbitMQ cluster, which has
permissions to listen for notifications from OpenStack components. At this
time it is listening to keystone and ironic only.
1. [External Secrets][eso] Secret Store to allow access the
   following secrets:

    - an OpenStack user our workflows can use
    - a Nautobot token our workflows can use

1. An [Argo Events][argo-events] Event Bus
to push the received notifications into.
1. A Kubernetes Service account `sensor-submit-workflow` which
allows an Argo Events Trigger from a Sensor to read look up
[Argo Workflows][argo-wf] Workflow Templates and use them to
execute a Workflow.
1. An [Argo Events][argo-events] Sensors and Triggers that
execute workflows.

### workflows/argo-events

This is where Kubernetes manifests are stored for the actual workflow
templates.

1. A webhook for a [Nautobot Webhook][nb-webhook] to submit events to [Argo Workflows][argo-wf].
1. An [Argo Events][argo-events] Event Bus to push the received notifications into.
1. A Kubernetes Service account `sensor-submit-workflow` which
allows an Argo Events Trigger from a Sensor to read look up
[Argo Workflows][argo-wf] Workflow Templates and use them to
execute a Workflow.
1. A Kubernetes Role Binding allowing the `sensor-submit-workflow`
Service Account access it needs to run Workflows.
1. An [Argo Events][argo-events] Sensors and Triggers that
execute workflows.
1. [Workflow Templates](./workflows/argo-events.md)

## Containers and Source Code

There are a number of containers built and used which are defined under
the `containers` top level path.

### python/understack-workflows

The code that is installed into the `ironic-nautobot-client` container
which is used for many of the workflows lives here.

[argo-events]: <https://argoproj.github.io/argo-events/>
[argo-wf]: <https://argo-workflows.readthedocs.io/en/latest/>
[eso]: <https://external-secrets.io>
[nb-webhook]: <https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/webhook/>
