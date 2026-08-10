<!--
Pull request titles must follow conventional commits and are checked by CI:
  feat|fix|docs|test|ci|chore(optional-scope): description
Append `!` (for example `feat(neutron)!:`) for a change that requires operator
action to upgrade.
-->

## What does this change do?

## Upgrade impact

- [ ] This change requires operator action to upgrade. If checked, add the
      `upgrade-impact` label and a release note: run `scriv create` from the
      repository root and describe the required action in the generated
      `changelog.d/` file. See [RELEASING.md](../RELEASING.md).

Operator action means anything a deployment has to do beyond a normal resync:
deploy repo or values changes, new or removed secrets, enabling or disabling a
component, or a manual one-time step.
