# Understack Workflows

This is the Kubernetes installation of the Argo Workflows
and their associated support bits to add the actual workflows,
sensors and triggers into a Kubernetes cluster.

Due to the scoping of resources into different namespaces, this
must also be split into multiple namespaces.

This code lives in `apps/understack-workflows` of this repo.

Specifics about the workflows can be seen in the Workflows
section.

## eventsource-openstack

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

## workflowtemplates

1. A Kubernetes Role Binding allowing the `sensor-submit-workflow`
the access it needs to run Workflows.
1. A number of Workflow Templates.

[argo-events]: <https://argoproj.github.io/argo-events/>
[argo-wf]: <https://argo-workflows.readthedocs.io/en/latest/>
[eso]: <https://external-secrets.io>
