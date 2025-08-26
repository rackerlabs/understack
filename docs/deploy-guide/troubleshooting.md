# Deployment Troubleshooting

We have documentation for individual components in the [Operator Guide](../operator-guide/index.md).

## ArgoCD Stuck Syncing

We have seen ArgoCD can sometimes become "stuck" while processing deployments. Sometimes
this can be due to the app component running a kubernetes job which gets stuck indefinitely.

For example, some openstack-helm components have init jobs which depends on other steps being
completed or may have a misconfiguration, where the init will loop forever. In argo you can
see what jobs are stuck, then check the kubernetes job pod logs for further details. Note that
a lot of OpenStack pods may have multiple containers, so interesting logs may not be in the
default container output.

In argo, we've also seen it can be helpful to terminate an old sync and issue a new sync.
