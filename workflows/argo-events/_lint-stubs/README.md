# Lint stubs

Placeholder `WorkflowTemplate` manifests used **only** by the
`Lint Workflow Templates` GitHub Actions workflow
(`.github/workflows/lint-workflow-templates.yaml`).

## Why this exists

Some templates in `../workflowtemplates/` reference WorkflowTemplates that are
**not** part of this repository. They are site-specific extensions installed
from `undercloud-deploy`, and only where a site opts in. For example,
`enroll-server.yaml` references `enroll-post-hook` via `templateRef`.

`argo lint` resolves `templateRef` names against the cluster. In CI the lint
runs against a throwaway kind cluster that only has this repo's templates
deployed, so any external reference fails to resolve and the lint reports a
false failure.

To keep the lint meaningful without weakening it, the CI job deploys every stub
in this directory into the lint namespace before running `argo lint`. That lets
the external references resolve against a minimal placeholder.

## Rules

- These files are **lint-only**. They are never deployed to a real environment.
- Keep each stub minimal: the correct `kind`, `metadata.name`, and the
  referenced template name plus its declared inputs are all that matter.
- This directory is prefixed with `_` so it is not picked up by the lint loop,
  which globs `../workflowtemplates/*.yaml`.

## Adding a new external reference

When a template here starts referencing an out-of-repo WorkflowTemplate, add a
matching stub file in this directory. No change to the CI workflow is needed.
