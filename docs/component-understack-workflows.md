# Understack Workflows

Understack Workflows is a collection of code, scripts, container definitions
centered around [Argo Workflows][argo-wf] to drive automated operations
based on events and other triggers in the system.

Due to the scoping of resources into different namespaces in the deployment
it is also split into multiple namespaces.

Specifics about each workflow can be seen in the Workflows
section.

## workflows/openstack

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

## workflows/argo-events

This is where Kubernetes manifests are stored for the actual workflow
templates.

1. A Kubernetes Role Binding allowing the `sensor-submit-workflow`
the access it needs to run Workflows.
1. [Workflow Templates](./workflows/argo-events.md)

## python/understack-workflows

The code that is installed into the `ironic-nautobot-client` container
which is used for many of the workflows lives here.

[argo-events]: <https://argoproj.github.io/argo-events/>
[argo-wf]: <https://argo-workflows.readthedocs.io/en/latest/>
[eso]: <https://external-secrets.io>
