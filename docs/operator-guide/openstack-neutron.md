# Neutron

## Router Flavors and VRF VNI Allocation

UnderStack uses Neutron [router flavors][ovn-router-flavors] to offer several
kinds of routers, each backed by an L3 service provider. For the fabric VRF
flavors, a VXLAN **VNI** is additionally attached to the router and tracked by
the `understack_vni` L3 service plugin.

For the design background on routing in the fabric, see the
[Neutron Networking design guide](../design-guide/neutron-networking.md#routing-network-traffic).

### Router flavors

Each router flavor is bound to a **service profile**, and each service profile
names an L3 service provider `driver`. The providers we register (see
`components/neutron/values.yaml`) are:

| Flavor         | Provider driver                                   | Purpose                                   |
|----------------|---------------------------------------------------|-------------------------------------------|
| `dynamic_vrf`  | `neutron_understack.l3_router.vrf.Vrf`            | Fabric VRF, VNI auto-allocated for users  |
| `static_vrf`   | `neutron_understack.l3_router.vrf.Vrf`            | Fabric VRF, VNI supplied by an admin       |
| `svi`          | `neutron_understack.l3_router.svi.Svi`            | On-fabric SVI gateway                     |
| `palo-alto`    | `neutron_understack.l3_router.palo_alto.PaloAlto` | Physical Palo Alto (stub)                 |
| `cisco-asa`    | `neutron_understack.l3_router.cisco_asa.CiscoAsa` | Physical Cisco ASA (stub)                 |

`dynamic_vrf` and `static_vrf` share the **same** provider driver (`Vrf`). What
differs between them is a piece of **service-profile metainfo**, `vni_alloc`,
described below.

### The `evpn_vni` attribute

The `understack_vni` L3 service plugin adds an `evpn_vni` attribute to routers.
When a VNI is allocated for a router it is recorded in UnderStack's own
allocation table and surfaced on the router as `evpn_vni`.

Two important defaults govern the behaviour:

* The `evpn_vni` attribute defaults to **`ATTR_NOT_SPECIFIED`** (not `0`). A bare
  `router create` therefore leaves the attribute unspecified, so neither
  UnderStack nor Neutron core auto-allocates a VNI unless something opts in. This
  is what prevents *every* router (including non-VRF flavors such as Palo Alto)
  from silently receiving a VNI.
* Supplying `evpn_vni` explicitly is gated by the `create_router:evpn_vni`
  policy, which defaults to **admin only**.

### The `vni_alloc` metainfo toggle

Whether — and how — a router of a given flavor gets a VNI is controlled by a
`vni_alloc` key in that flavor's service-profile **metainfo** (stored as a JSON
string). It has three values:

| `vni_alloc` | No `evpn_vni` supplied      | Explicit `evpn_vni` supplied            |
|-------------|-----------------------------|-----------------------------------------|
| `off` *(default)* | no VNI allocated      | **rejected** (`BadRequest`)             |
| `on`        | no VNI allocated            | that specific VNI is allocated          |
| `auto`      | a VNI is auto-allocated     | that specific VNI is allocated          |

Notes:

* **Default is `off`.** A flavor with no metainfo, no `vni_alloc` key, an
  unrecognised value, or no flavor at all is treated as `off`. Invalid values
  are logged (a warning in `neutron-server`) and fall back to `off`.
* The metainfo must be **valid JSON describing an object**, e.g.
  `{"vni_alloc": "auto"}`. Neutron does not validate metainfo; UnderStack parses
  it, and anything that is not valid JSON is ignored (falls back to `off`).
* `vni_alloc` lives on the **service profile**, not the flavor. Because
  `dynamic_vrf` and `static_vrf` need different values, they must be bound to
  **different** service profiles even though both use the `Vrf` driver.

#### Auto-allocation pool

Auto-allocated VNIs (`vni_alloc: auto`) come from the range configured in the
`[understack_vni] vni_ranges` option (comma-separated single VNIs or
`start:end` ranges). It defaults to `1:16777215`. Set it in the Neutron config
to scope allocation to the range your fabric reserves for VRFs, for example:

```ini
[understack_vni]
vni_ranges = 100000:199999
```

### Configuring `static_vrf` and `dynamic_vrf`

The two VRF flavors need one service profile each, differing only in
`vni_alloc`.

**1. Inspect current bindings.** Both VRF flavors are likely bound to a single
shared `Vrf` service profile today (which carries no metainfo, i.e. `off`):

```bash
openstack network flavor show dynamic_vrf   # note service_profile_ids
openstack network flavor show static_vrf
```

**2. Create one `Vrf` service profile per mode.**

```bash
# auto-allocate — for dynamic_vrf
openstack network flavor profile create \
  --driver neutron_understack.l3_router.vrf.Vrf \
  --metainfo '{"vni_alloc": "auto"}' \
  --description "Dynamic Fabric VRF (auto VNI)"

# admin-supplied only — for static_vrf
openstack network flavor profile create \
  --driver neutron_understack.l3_router.vrf.Vrf \
  --metainfo '{"vni_alloc": "on"}' \
  --description "Static Fabric VRF (admin-supplied VNI)"
```

**3. Bind each flavor to exactly one profile.** Remove the old shared profile
binding first so `get_flavor_next_provider` resolves the intended one:

```bash
openstack network flavor remove profile dynamic_vrf <OLD_SHARED_PROFILE_ID>
openstack network flavor add    profile dynamic_vrf <AUTO_PROFILE_ID>

openstack network flavor remove profile static_vrf  <OLD_SHARED_PROFILE_ID>
openstack network flavor add    profile static_vrf  <ON_PROFILE_ID>
```

<!-- markdownlint-capture -->
<!-- markdownlint-disable MD046 -->
!!! tip

    Bind each flavor to a **single** service profile. `get_flavor_next_provider`
    uses the first binding to resolve the provider driver, and the `vni_alloc`
    lookup uses the first profile that carries metainfo — multiple bindings make
    both ambiguous.
<!-- markdownlint-restore -->

### Creating routers

* **`dynamic_vrf`** — any authorised user can create one and a VNI is
  auto-allocated:

    ```bash
    openstack router create --flavor <dynamic_vrf-flavor-id> my-router
    ```

* **`static_vrf`** — an admin creates the router and supplies the VNI. Because
  `create_router:evpn_vni` is admin-only, non-admins cannot set `evpn_vni`; a
  `static_vrf` router created without a VNI simply gets none. Setting `evpn_vni`
  requires an extension-aware client or a direct API call, as it is a custom
  router attribute.

### Retiring the `vrf` flavor

Once `dynamic_vrf` / `static_vrf` cover both cases, disable then delete the old
`vrf` flavor and its now-unused stub profile:

```bash
openstack network flavor set --disable vrf
openstack network flavor delete vrf
# once nothing is bound to it:
openstack network flavor profile delete <OLD_VRF_STUB_PROFILE_ID>
```

### Troubleshooting VNI allocation

#### A router was created but got no VNI

* Confirm the flavor's service profile metainfo: `openstack network flavor
  profile show <profile-id>`. With `vni_alloc: off` (or missing) no VNI is
  allocated. Use `auto` (or supply a VNI under `on`).
* Confirm the flavor is bound to the profile you edited, not a different/older
  one: `openstack network flavor show <flavor>`.
* For `on` mode, a VNI is allocated **only** when one is explicitly supplied and
  the caller is an admin (per `create_router:evpn_vni`).

#### `BadRequest: evpn_vni cannot be set on routers of this flavor`

The flavor resolves to `vni_alloc: off`. Either the flavor is not meant to carry
a VNI, or its service profile is missing `{"vni_alloc": "on"}` /
`{"vni_alloc": "auto"}`. Fix the metainfo, or don't pass `evpn_vni`.

#### Every router unexpectedly receives a VNI

This was the pre-fix behaviour (the attribute defaulted to `0`, which Neutron
core read as an auto-allocate request). Ensure you are running a build with the
`ATTR_NOT_SPECIFIED` default, and that only the intended flavor's profile has
`vni_alloc: auto`. A shared profile with `auto` will affect every flavor bound
to it.

#### `UnderstackVNINoAvailable: No Understack VNI is available`

The `[understack_vni] vni_ranges` pool is exhausted. Widen the range, or release
VNIs by deleting routers that no longer need them (deleting a router releases its
VNI for reuse).

#### Metainfo changes seem to have no effect

* Metainfo must be valid JSON: `{"vni_alloc": "auto"}`, not `vni_alloc=auto`.
  Invalid JSON is ignored and the flavor falls back to `off`; look for an
  `Ignoring non-JSON metainfo` or `invalid vni_alloc` warning in the
  `neutron-server` log.
* A service profile that is **in use** by a flavor cannot be updated; unbind it,
  update, and rebind, or create a new profile and rebind the flavor to it.

#### Inspecting the VNI on a router

The allocated VNI appears as the `evpn_vni` field on the router (visible to
admins and the owning project reader per `get_router:evpn_vni`). Use an
extension-aware client or the API to read it.

## Debugging Neutron

### Debugging ML2

To debug ML2 and see the messages that are flowing into the ML2
mechanism you can add the following snippet into your `neutron.yaml`
for your environment.

```yaml
conf:
  plugins:
    ml2_conf:
      ml2:
        # this line just aims to add 'logger' but its
        # replacing so you'll need to pay attention
        # to any changes your environment might have
        # from the default
        mechanism_drivers: "logger,ovn,understack,baremetal,undersync"
  logging:
    loggers:
      # for 'keys' we are attempt to append 'mechanism_logger'
      # but the way YAML are merged you will need to include
      # all other items in the list here as well.
      keys:
        - ...
        - mechanism_logger
    logger_mechanism_logger:
      level: DEBUG
      handlers: stdout
      qualname: mechanism_logger
```

Once you deploy this the `neutron-server` pod will now log everything that the
ML2 drivers receive. The log line will have `called with network settings` in it.
That message will be prefixed with the ML2 method name like `create_network_postcommit`.

[ovn-router-flavors]: <https://specs.openstack.org/openstack/neutron-specs/specs/2023.2/ml2ovn-router-flavors.html>
