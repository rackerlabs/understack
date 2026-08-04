# RBAC Scope and Image Ownership

Three things interact in ways that are easy to get wrong: Ironic's node
ownership model, the Keystone scope a service authenticates with, and which
project owns the IPA deploy images in Glance.

The short version is that **Ironic and Glance need different scopes**, so the
service credentials in `ironic.conf` are deliberately not uniform. Ironic wants
system scope for cross-tenant node management; Glance will reject a
system-scoped token outright, so its client credentials have to stay
project-scoped.

## Node ownership model

Ironic tracks two project references on each node:

- **`node.owner`** — the DC operator's project. It owns the physical asset and
  does the work that goes with that: inspection, cleaning, BIOS and firmware
  configuration.
- **`node.lessee`** — optional. A tenant that has been leased direct
  Ironic-level access to the node without owning it.

Regular tenants never call Ironic directly. They go through Nova, and Nova's
`ironic` virt driver talks to Ironic using the **service user's** credentials.
So from Ironic's point of view a tenant instance build arrives as a service
request, not as a request from the tenant's project.

## How Ironic evaluates scope

Ironic's secure RBAC policies (`is_node_owner`, `is_node_lessee`) compare the
token's `project_id` against `node.owner` and `node.lessee`. Two consequences:

- A **project-scoped** token only gets access to nodes whose `owner` or
  `lessee` matches that project.
- A **system-scoped** `admin`, `member` or `reader` token **bypasses the
  ownership checks entirely** and can see and act on every node.

This deployment already overrides some of these policies. See
`components/ironic/values.yaml` under `conf.policy`, where the console policies
are written to accept either a system-scoped role or a project match against
`node.owner` / `node.lessee`:

```text
"baremetal:node:get_console":
  ((role:member and system_scope:all) or rule:service_role)
  or (role:service and system_scope:all)
  or (role:member and project_id:%(node.owner)s)
  or (role:service and project_id:%(node.owner)s)
  or (role:member and project_id:%(node.lessee)s)
```

That is the shape to follow when adding policy overrides: allow the
system-scoped service path **and** the owner/lessee project path.

## Why service users should be system-scoped

`ironic-conductor` and `nova-compute`'s ironic driver manage nodes across every
tenant. If they authenticate with a project-scoped token they become subject to
per-node owner/lessee matching, which is exactly the wrong behaviour for an
infrastructure service — a node owned by one DC operator project would be
invisible to them.

So they should authenticate as **system-scoped**. In practice that means using
`system_scope = all` and dropping `project_name` and `project_domain_id` from
the relevant sections.

## The Glance exception

**Glance dropped system-scope support.** Its policies are project-only: they
match `role:reader` or `role:member` against the image's own project, or fall
back to the image's `community`, `public` or `shared` visibility. A
system-scoped token does not satisfy any of those, so **Glance answers a
system-scoped request with a 403.**

That makes the `[glance]` section a genuine exception. It has to stay
project-scoped to the service project even while the sections around it use
system scope.

## Configuration example

Both scopes side by side in a single `ironic.conf`. Note that `[glance]` is the
odd one out, and that this is deliberate rather than an oversight — worth a
comment in your own config so nobody "fixes" it later.

```ini title="ironic.conf"
# ---------------------------------------------------------------------------
# System-scoped: not subject to per-node owner/lessee project matching.
# ---------------------------------------------------------------------------

[keystone_authtoken]
auth_type = password
auth_url = https://keystone.example.com/v3
user_domain_name = service
username = ironic
password = <redacted>
# System scope. Deliberately no project_name / project_domain_id.
system_scope = all

[service_catalog]
auth_type = password
auth_url = https://keystone.example.com/v3
user_domain_name = service
username = ironic
password = <redacted>
system_scope = all

[neutron]
auth_type = password
auth_url = https://keystone.example.com/v3
user_domain_name = service
username = ironic
password = <redacted>
system_scope = all

[nova]
auth_type = password
auth_url = https://keystone.example.com/v3
user_domain_name = service
username = ironic
password = <redacted>
system_scope = all

# ---------------------------------------------------------------------------
# Project-scoped: Glance has no system-scope support. A system-scoped token
# here returns 403. This section must stay scoped to the project that owns
# the IPA deploy images.
# ---------------------------------------------------------------------------

[glance]
auth_type = password
auth_url = https://keystone.example.com/v3
user_domain_name = service
username = ironic
password = <redacted>
# Project scope, NOT system_scope. Do not "clean this up" to match the
# sections above -- Glance will start returning 403 on deploy.
project_domain_name = service
project_name = service
```

Nova's side needs the same treatment. In `nova.conf`, the `[ironic]` section
that nova-compute uses to reach the Ironic API should also be system-scoped:

```ini title="nova.conf"
[ironic]
auth_type = password
auth_url = https://keystone.example.com/v3
user_domain_name = service
username = ironic
password = <redacted>
system_scope = all
```

### Expressing this in UnderStack

This deployment does not hand-write `ironic.conf`. The file is rendered by
OpenStack-Helm from the `conf.ironic` tree, so each `ini` section above becomes
a key under `conf.ironic` in your deploy repo overrides:

```yaml title="$CLUSTER_NAME/ironic/values.yaml"
conf:
  ironic:
    keystone_authtoken:
      system_scope: all
    service_catalog:
      system_scope: all
    neutron:
      system_scope: all
    nova:
      system_scope: all
    # Glance stays project-scoped -- see above.
    glance:
      project_domain_name: service
      project_name: service
```

Setting a key to `null` removes it, which is how you drop the
`project_name` that OpenStack-Helm supplies by default in the system-scoped
sections.

## IPA deploy image ownership

The IPA kernel and ramdisk should be owned by the **service project and
domain**, not by the DC-operator project that owns the node.

The reasoning is about what these artifacts are. They are infrastructure, not
tenant data. `ironic-conductor` pulls them from Glance using the service user's
project-scoped credentials during deploy, clean and rescue. The project named
in `node.owner` never touches Glance to fetch them, so giving that project
ownership buys nothing and couples image access to node ownership.

Any of these work:

- Own the images in the service project and set visibility to `community` or
  `public`.
- Or use `shared` visibility and explicitly add the service project as a member.

The first is simpler. Use `shared` plus member-add only if you genuinely need to
restrict which projects can see the deploy artifacts.

Note the distinction from **tenant** images such as the Ubuntu cloud image.
Those are ordinary user-facing images and follow normal visibility rules; none
of the above applies to them.

## Current state in this deployment

The model above is the target. Some of it is not yet what the repository does,
so check before assuming:

- **Service user roles are project-scoped.**
  `components/ironic/ironic-ks-user-baremetal.yaml` grants the Ironic service
  user `admin` and `service` with `--project-domain infra --project baremetal`.
  There is no system-scoped role assignment.
- **No `system_scope` is set anywhere** in `components/ironic/values.yaml`.
  The service sections inherit OpenStack-Helm's project-scoped defaults.
- **The IPA artifacts are uploaded private.** In
  `ansible/roles/openstack_glance_image_upload/defaults/main.yml`, `esp.img`,
  `ipa-debian-bookworm.kernel` and `ipa-debian-bookworm.initramfs` are all
  `is_public: false`, and the role sets no owner, so they end up owned by
  whichever project ran the playbook. By contrast the tenant image
  (`Ubuntu 24.04`) is `is_public: true`.

Moving to the target model means granting the service user a system-scoped role
assignment, adding the `system_scope` overrides, and republishing the IPA
artifacts under the service project with `community` or `public` visibility.

Each of those changes an existing deployment has to act on, and none of them
take effect from a resync alone, so each needs upgrade notes telling operators
what to run and in what order. Sequence matters: grant the system-scoped role
assignment **before** switching the config to `system_scope = all`, or the
conductor loses access on restart.

## Debugging a 403

If a deploy fails fetching the IPA kernel or ramdisk and Glance logs a 403, work
through it in this order:

1. Check whether the `[glance]` section acquired a `system_scope`. That is the
   most likely cause, and it usually happens when someone makes the sections
   uniform.
2. Check the image's `owner` against the project in `[glance]`.
3. Check the image's `visibility`. If it is `private` and owned by a different
   project, the conductor cannot read it — make it `community`, `public`, or
   `shared` with the service project added as a member.

If Ironic instead reports a node as not found, or a node is invisible to
`nova-compute` while visible to an operator token, that is the opposite problem:
a service credential is project-scoped where it should be system-scoped, and
owner/lessee matching is filtering the node out.

## Summary

Ironic's API scope and Glance's image-access scope are configured
independently, and they end up different on purpose:

| Client | Scope | Why |
| --- | --- | --- |
| Ironic API, Neutron, Nova, service catalog | `system_scope = all` | Cross-tenant node management must not be filtered by `node.owner` / `node.lessee`. |
| Glance | project-scoped to `service` | Glance has no system-scope support and returns 403; the scope must match where the IPA images live. |
