# Argo Workflows

The UnderStack project utilizes [Argo Workflows][argo-wf] as its
workflow orchestration engine for managing complex, multi-step
operations across the infrastructure stack. [Argo Workflows][argo-wf]
provides a Kubernetes-native approach to defining and executing
workflows, enabling reliable automation of provisioning, deployment,
and maintenance tasks.

## Architecture & Security Model

[Argo Workflows][argo-wf] operates within a dedicated namespace (argo),
while the actual workflows run in another dedicated namespace (argo-events),
to ensure proper security isolation and resource control. This separation
is provided by [Argo Workflows][argo-wf] but poorly documented upstream which
they call [Managed Namespace][argo-wf-managed-ns]. Unfortunately the
likely better approach at achieving this managed namespace installation
would be to use the cluster based install which uses ClusterRoles but then
binds the ClusterRole to a specific namespace instead of a ClusterRoleBinding.
This is the approach we take.

### Argo Workflows Configuration

We do not use the `namespace-install.yaml` provided by the project as it
combines everything into one YAML and focuses on running everything in
one namespace while we want separation. What we ultimately need:

* CRDs
* Argo Server, which is the UI and the API for Argo Workflows and Argo Events
* Argo Workflows Controller, which is the executor for the workflow and creates
the pods
* Server RBAC, which is the ClusterRole and RoleBinding for the Argo Server to access
the workflow, the pods, the logs, and inputs for user visibility
* Workflow Controller RBAC, which is the ClusterRole and RoleBinding to give the controller
access to run and manage the workflows.

The CRDs, the Argo Server, and the Argo Workflow Controller will all be installed
into the (argo) namespace while the 2 RoleBindings need to be installed
into the namespace where the workflow execute, which is (argo-events).

The Argo Server and the Workflow Controller additionally need access to additional
resources. The Argo Server needs access to the configmap, the SSO secret.

## Template-Only Execution Model

Understack enforces a strict template-only execution model where all workflows
must be pre-defined as [WorkflowTemplate][argo-wf-tmpl]s. This approach ensures:

* Consistency: All workflows follow approved patterns and standards
* Security: No arbitrary workflow submission; all templates are reviewed and versioned
* Reusability: Common operations are defined once and parameterized for different
use cases
* Governance: Changes to workflows go through code review and CI/CD processes

[argo-wf]: <https://argo-workflows.readthedocs.io/en/latest/>
[argo-wf-managed-ns]: <https://argo-workflows.readthedocs.io/en/stable/managed-namespace/>
[argo-wf-tmpl]: <https://argo-workflows.readthedocs.io/en/stable/workflow-templates/>
