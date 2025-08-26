# Load Balancer Configuration

If you decide to use Octavia Load Balancers there is a post-install ansible
playbook which sets up networks, security groups, and ports for octavia's
use.

The ansible playbook is `understack/ansible/playbooks/openstack_octavia.yaml`
and it gets triggered after ArgoCD successfully syncs the octavia component
from an ArgoCD post sync hook:

``` yaml
metadata:
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
```

The post-sync job is `components/octavia/octavia-post-deployment-job.yaml`.
