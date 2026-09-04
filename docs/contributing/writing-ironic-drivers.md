# Writing Ironic Drivers and Interfaces

This page is for contributors adding or changing bare metal behavior in
`ironic-understack`, UnderStack's Ironic plugin package. It assumes no prior
Ironic knowledge. If you already know Ironic well, skip to
[How UnderStack plugs in](#how-understack-plugs-in).

## Ironic in a nutshell

Ironic manages physical servers ("nodes") the way Nova manages virtual
machines. A node's behavior is defined by a **driver**, and a driver is built
from two things:

- A **hardware type** — a Python class that says which vendor/family of
  hardware this is (generic Redfish, iDRAC, a network switch, ...).
- A set of **hardware interfaces** — one implementation per concern: `power`,
  `management`, `boot`, `deploy`, `inspect`, `raid`, `bios`, `network`,
  `storage`, `rescue`, `firmware`, `vendor`, `console`. Each interface answers
  one question, e.g. "how do I power this on?" or "how do I find out what
  hardware this is?"

Both are loaded via Python entry points and enabled by name in `ironic.conf`
(`enabled_hardware_types`, `enabled_<interface>_interfaces`). This is what lets
UnderStack ship its own hardware types and interfaces as a separate package
without forking Ironic itself.

Read these two upstream pages before writing any code — this page does not
repeat their content:

- [Drivers](https://docs.openstack.org/ironic/latest/admin/drivers.html) — the
  catalog of hardware types and interfaces Ironic ships, and how they combine.
- [Features](https://docs.openstack.org/ironic/latest/admin/features.html) —
  what Ironic can do end to end (deployment, cleaning, RAID, rescue, etc.).
- [Pluggable Drivers](https://docs.openstack.org/ironic/latest/contributor/drivers.html)
  — upstream's own guide to subclassing a hardware type or interface. Everything
  it says about `AbstractHardwareType`, `PowerInterface`,
  `ManagementInterface`, etc. applies unchanged inside `ironic-understack`.

## The node state machine

A node's lifecycle is a state machine — `available`, `deploying`, `active`,
`cleaning`, `manageable`, and so on — documented in full at
[Bare Metal State Machine](https://docs.openstack.org/ironic/latest/user/states.html).
Interfaces and hooks are the code that runs *during* specific state
transitions, so knowing which transition you're targeting tells you which
interface to touch.

### The four operations we care about

Most of the work UnderStack contributors do lands in one of four operations:

1. **Inspecting** — discovering what a node actually is: CPU, memory, disks,
   NICs, chassis model. Driven by the `inspect` interface
   (`inspect_hardware()`), plus an `ironic.inspection.hooks` pipeline that
   post-processes the inventory data the ramdisk reports before it's saved to
   the node. This is where UnderStack matches a node to a flavor and resource
   class — see [`redfish_inspect_understack.py`](#writing-a-new-hardware-interface)
   below.
2. **Cleaning** — wiping disks and resetting BIOS/RAID/firmware settings
   between tenants, or before first use. Implemented as **clean steps**:
   methods decorated with `@ironic.drivers.base.clean_step(priority=...)` on
   whichever interface owns that action (`management`, `deploy`, `raid`, ...).
   Runs in the `cleaning` state. If the device has no deploy ramdisk to boot
   (true of most network gear), every clean step it defines must pass
   `requires_ramdisk=False` — see
   [Interfaces for devices with no ramdisk or BMC agent](#interfaces-for-devices-with-no-ramdisk-or-bmc-agent).
3. **Deploying** — writing the tenant's image and configuration to the node.
   Implemented as **deploy steps**
   (`@ironic.drivers.base.deploy_step(priority=...)`), conventionally at
   priority 100 for the main deploy method. Runs in the `deploying` state.
4. **Servicing** — post-deployment maintenance (e.g. a firmware update) on a
   node that's already active, without a full teardown/redeploy. Implemented
   as **service steps** (`@ironic.drivers.base.service_step(...)`), explicitly
   requested by the caller rather than run automatically. Runs in the
   `servicing` state.

Clean, deploy, and service steps share the same shape: synchronous steps
return `None` and the conductor moves on; asynchronous steps return the
matching `WAIT` state and later call back (`continue_node_clean`,
`continue_node_deploy`, `continue_node_service`) to resume. `ironic-understack`
doesn't define any custom steps of these three kinds today — if you're adding
one, read the decorator docstrings in `ironic/drivers/base.py` and the
upstream [deploy steps guide](https://docs.openstack.org/ironic/latest/contributor/deploy-steps.html)
first.

## How UnderStack plugs in

`ironic-understack` ([`python/ironic-understack/`](https://github.com/rackerlabs/understack/tree/main/python/ironic-understack))
is an ordinary Python package that Ironic loads via entry points, declared in
its `pyproject.toml`:

| Entry point group | What it's for | UnderStack examples |
| --- | --- | --- |
| `ironic.hardware.types` | New hardware type | `netdev` |
| `ironic.hardware.interfaces.inspect` | New `inspect` interface implementation | `redfish-understack`, `idrac-redfish-understack` |
| `ironic.inspection.hooks` | Post-processing step for inspection data | `resource-class`, `update-baremetal-port`, `port-bios-name`, `node-name-check`, `chassis_model` |
| `ironic.api.middleware` | WSGI middleware on the Ironic API | `portgroup-name-validation` |
| `ironic.console.container` | Alternate console container backend | `kubernetes` |

The package is baked into the Ironic container image at build time
(`COPY python/ironic-understack ...` in
[`containers/ironic/Dockerfile`](https://github.com/rackerlabs/understack/blob/main/containers/ironic/Dockerfile)),
so a new driver or interface needs both a code change here and a container
rebuild before it's live — check [`README.md`](https://github.com/rackerlabs/understack/blob/main/python/ironic-understack/README.md)
and [`DEVELOPMENT.md`](https://github.com/rackerlabs/understack/blob/main/python/ironic-understack/DEVELOPMENT.md)
for the local dev loop.

For UnderStack's existing shipped hardware types, see the
[Ironic design reference](../design-guide/ironic.md).

## Writing a new hardware interface

Use this when an existing interface (Redfish, iDRAC, IPMI, ...) is *almost*
right but needs UnderStack-specific behavior layered on top. The pattern used
throughout `ironic_understack/drivers/` is a mixin over the upstream class,
registered under the same entry point group as the interface you're
extending.

`ironic_understack/drivers/redfish_inspect_understack.py` extends the stock
Redfish and iDRAC-Redfish `inspect` interfaces to match discovered hardware
against a flavor:

```python
class FlavorInspectMixin:
    def inspect_hardware(self, task):
        upstream_state = super().inspect_hardware(task)
        # ... read inspection data, match a flavor, set task.node.resource_class
        return upstream_state


class UnderstackRedfishInspect(FlavorInspectMixin, RedfishInspect):
    ...


class UnderstackDracRedfishInspect(FlavorInspectMixin, DracRedfishInspect):
    ...
```

The steps to follow this pattern for a different interface (say, a custom
`management` behavior):

1. Pick the upstream class you're extending, e.g.
   `ironic.drivers.modules.redfish.management.RedfishManagement`.
2. Subclass it (with a mixin if the same logic should apply to more than one
   base class), calling `super().<method>(task)` and only adding what's
   different.
3. Register it under the matching entry point group in `pyproject.toml`, e.g.:

   ```toml
   [project.entry-points."ironic.hardware.interfaces.management"]
   my-management-understack = "ironic_understack.drivers.my_module:MyManagement"
   ```

4. Add it to `enabled_management_interfaces` in `ironic.conf` and to the
   relevant hardware type's `supported_management_interfaces` list (see
   below) so Ironic actually picks it up.
5. Write a unit test alongside the existing ones in
   `ironic_understack/tests/` — run with `pytest` (or `uv run pytest`) from
   `python/ironic-understack/`.

If you only need to react to inspection data rather than replace the whole
`inspect` interface, prefer an **inspection hook**
(`ironic.inspection.hooks`, see `ironic_understack/hooks/`) — it's a smaller
surface: implement `InspectionHook.__call__(self, task, inventory,
plugin_data)` and register it, no interface subclassing required.

## Interfaces for devices with no ramdisk or BMC agent

The pattern above — mix in over `RedfishInspect`/`RedfishManagement` — only
works when the device speaks Redfish (or IPMI, or has a sushy-compatible BMC).
A lot of the hardware UnderStack needs to manage doesn't: network gear like
switches and firewalls is typically managed out-of-band over SSH or a
vendor API, and never boots an Ironic deploy ramdisk at all. For that class of
device you write the interface from scratch against the abstract base
classes, not as a mixin over an existing implementation.

`netdev_hardware.py`'s `NetdevHardware` (above) is **not** a template for
this — it wires every interface to a no-op precisely because it does no real
inspection or management. A device you actually want to inspect and clean
needs real implementations behind those two interfaces.

**Inspect, from scratch.** Subclass `ironic.drivers.base.InspectInterface`
directly and implement the one abstract method, `inspect_hardware`. Nothing
requires a ramdisk here — everything is driven by however you talk to the
device (SSH, a vendor API, SNMP, ...):

```python
from ironic.common import exception
from ironic.common import states
from ironic.drivers import base


class MyDeviceInspect(base.InspectInterface):
    # Override if "memory_mb"/"local_gb"/"cpu_arch" don't apply to this
    # device; leave empty rather than reporting properties that don't exist.
    ESSENTIAL_PROPERTIES = set()

    def get_properties(self):
        return {}

    def validate(self, task):
        pass  # check that credentials/connection info are present

    def inspect_hardware(self, task):
        # Connect to the device, discover its properties/ports however is
        # appropriate for it, then persist what you found:
        #   task.node.properties = {...}
        #   task.node.save()
        # Create ironic Port objects for discovered NICs/interfaces as needed.
        if <inspection failed>:
            raise exception.HardwareInspectionFailure(...)
        return states.MANAGEABLE
```

**Cleaning, out-of-band.** Real cleaning behavior belongs on a real
`management` interface. You don't have to reimplement the boot-device
methods `ManagementInterface` requires (`get_supported_boot_devices`,
`set_boot_device`, `get_boot_device`) if they're meaningless for this
device — subclass `ironic.drivers.modules.noop_mgmt.NoopManagement` to inherit
sensible no-op defaults for those, then add your real clean step(s) on top.
The key detail is `requires_ramdisk=False`, since there's no ramdisk to wait
on:

```python
from ironic.drivers import base
from ironic.drivers.modules import noop_mgmt


class MyDeviceManagement(noop_mgmt.NoopManagement):
    def validate(self, task):
        pass  # check that credentials/connection info are present

    @base.clean_step(priority=10, requires_ramdisk=False)
    def reset_to_factory_defaults(self, task):
        # Talk to the device and reset its configuration. Return None when
        # done (synchronous); return states.CLEANWAIT and later call
        # continue_node_clean() if the reset is asynchronous.
        ...
```

Wire both into a new hardware type (a sibling to `NetdevHardware`, not a
modification of it) via `supported_inspect_interfaces` and
`supported_management_interfaces`, register the entry points, and enable them
— same steps as [Writing a new hardware interface](#writing-a-new-hardware-interface)
and [Writing a new hardware type](#writing-a-new-hardware-type) above. Test
the clean step by calling it directly against a mocked connection/task, the
same way `test_netdev_hardware.py` tests interface selection without a
running Ironic service.

## Writing a new hardware type

Use this when a class of node needs a genuinely different combination of
interfaces, not just a tweak to one of them.
`ironic_understack/drivers/netdev_hardware.py` is UnderStack's example — a
hardware type for network devices that Ironic tracks only for Neutron port
binding, with every other interface set to a no-op:

```python
class NetdevHardware(generic.ManualManagementHardware):
    @property
    def supported_deploy_interfaces(self):
        return [noop.NoDeploy]

    @property
    def supported_network_interfaces(self):
        return [neutron.NeutronNetwork]

    # ... one supported_<interface>_interfaces property per interface
```

To add your own:

1. Subclass `ironic.drivers.hardware_type.AbstractHardwareType`, or more
   usually `ironic.drivers.generic.GenericHardware` (or one of its variants
   like `ManualManagementHardware`) to inherit sane defaults for interfaces
   you don't need to change.
2. Override `supported_<interface>_interfaces` for each interface where the
   default isn't right, listing implementations in priority order (most
   preferred first).
3. Register it:

   ```toml
   [project.entry-points."ironic.hardware.types"]
   my-hardware = "ironic_understack.drivers.my_hardware:MyHardware"
   ```

4. Add it to `enabled_hardware_types` in `ironic.conf`, and make sure every
   interface it lists is also present in the corresponding
   `enabled_<interface>_interfaces` option.
5. Test it the way `ironic_understack/tests/test_netdev_hardware.py` does —
   instantiate the class directly and assert on
   `supported_<interface>_interfaces`, no running Ironic service required:

   ```python
   def test_netdev_deploy():
       hw = NetdevHardware()
       assert [c.__name__ for c in hw.supported_deploy_interfaces] == ["NoDeploy"]
   ```

## Where to go next

- [Ironic design reference](../design-guide/ironic.md) — what UnderStack
  ships today and why.
- [Enabling Drivers](https://docs.openstack.org/ironic/latest/install/enabling-drivers.html)
  — the operator side of `enabled_hardware_types` / `enabled_<interface>_interfaces`.
- [Bare Metal State Machine](https://docs.openstack.org/ironic/latest/user/states.html)
  — the full state diagram behind the "four operations" above.
- [`operator-guide/openstack-ironic-inspection-guide.md`](../operator-guide/openstack-ironic-inspection-guide.md)
  — how inspection behaves operationally in UnderStack today.
