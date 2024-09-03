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

[argo-events]: <https://argoproj.github.io/argo-events/>
[eso]: <https://external-secrets.io>
