#!/usr/bin/env python3
"""
Script to clean up storage-related objects in Nautobot for a specific tenant.

This script deletes VRF, Prefix, IPAddress, VirtualMachine objects belonging to a tenant,
then deletes the tenant itself. Supports dry-run mode by default.
"""

import argparse
import sys
import os
import uuid
import pynautobot
import traceback


def validate_uuid(uuid_string: str) -> str:
    """Validate that the provided string is a valid UUID."""
    try:
        uuid.UUID(uuid_string)
        return uuid_string
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{uuid_string}' is not a valid UUID")


def get_objects_to_delete(nb: pynautobot.api, tenant_uuid: str) -> dict:
    """Get all objects that belong to the tenant and need to be deleted."""
    objects = {"vrfs": [], "prefixes": [], "ip_addresses": [], "virtual_machines": []}

    try:
        # Get VRFs
        vrfs = nb.ipam.vrfs.filter(tenant_id=tenant_uuid)
        objects["vrfs"] = list(vrfs)

        # Get Prefixes
        prefixes = nb.ipam.prefixes.filter(tenant_id=tenant_uuid)
        objects["prefixes"] = list(prefixes)

        # Get IP Addresses
        ip_addresses = nb.ipam.ip_addresses.filter(tenant_id=tenant_uuid)
        objects["ip_addresses"] = list(ip_addresses)

        # Get Virtual Machines
        virtual_machines = nb.virtualization.virtual_machines.filter(
            tenant_id=tenant_uuid
        )
        objects["virtual_machines"] = list(virtual_machines)

        # Get UCVNIs
        ucvnis = nb.plugins.undercloud_vni.ucvnis.filter(tenant=tenant_uuid)
        objects["ucvnis"] = list(ucvnis)

    except Exception as e:
        print(f"Error retrieving objects: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    return objects


def print_objects_summary(objects: dict, tenant_uuid: str):
    """Print a summary of objects that will be deleted."""
    print(f"Objects to be deleted for tenant {tenant_uuid}:")
    print(f"  VRFs: {len(objects['vrfs'])}")
    print(f"  Prefixes: {len(objects['prefixes'])}")
    print(f"  IP Addresses: {len(objects['ip_addresses'])}")
    print(f"  Virtual Machines: {len(objects['virtual_machines'])}")
    print(f"  UCVNIs: {len(objects['ucvnis'])}")
    print()

    if objects["vrfs"]:
        print("VRFs:")
        for vrf in objects["vrfs"]:
            print(f"  - {vrf.name} ({vrf.id})")

    if objects["prefixes"]:
        print("Prefixes:")
        for prefix in objects["prefixes"]:
            print(f"  - {prefix.prefix} ({prefix.id})")

    if objects["ip_addresses"]:
        print("IP Addresses:")
        for ip in objects["ip_addresses"]:
            print(f"  - {ip.address} ({ip.id})")

    if objects["virtual_machines"]:
        print("Virtual Machines:")
        for vm in objects["virtual_machines"]:
            print(f"  - {vm.name} ({vm.id})")

    if objects["ucvnis"]:
        print("UCVNIs:")
        for ucvni in objects["ucvnis"]:
            print(f"  - {ucvni.display} ({ucvni.id})")
    print()


def delete_objects(nb: pynautobot.api, objects: dict, dry_run: bool = True) -> bool:
    """Delete all objects. Returns True if successful."""
    success = True
    deleted_count = 0
    skipped_count = 0

    # Delete in order: VMs, IPs, Prefixes, VRFs
    deletion_order = [
        ("virtual_machines", "Virtual Machines"),
        ("ip_addresses", "IP Addresses"),
        ("prefixes", "Prefixes"),
        ("vrfs", "VRFs"),
        ("ucvnis", "UCVNIs"),
    ]

    for obj_type, display_name in deletion_order:
        if objects[obj_type]:
            print(f"{'[DRY RUN] ' if dry_run else ''}Deleting {display_name}...")
            for obj in objects[obj_type]:
                try:
                    if dry_run:
                        print(
                            f"  Would delete: {getattr(obj, 'name', getattr(obj, 'address', getattr(obj, 'prefix', str(obj))))} ({obj.id})"
                        )
                    else:
                        obj.delete()
                        deleted_count += 1
                        print(
                            f"  Deleted: {getattr(obj, 'name', getattr(obj, 'address', getattr(obj, 'prefix', str(obj))))} ({obj.id})"
                        )
                except Exception as e:
                    error_msg = str(e)
                    # Check if this is a 404 error (object already deleted)
                    if "could not be found" in error_msg or "404" in error_msg:
                        skipped_count += 1
                        print(f"  Skipped: {obj.id} (already deleted)")
                    else:
                        print(f"  Error deleting {obj.id}: {e}", file=sys.stderr)
                        success = False

    if not dry_run and (deleted_count > 0 or skipped_count > 0):
        print(
            f"\nDeletion summary: {deleted_count} deleted, {skipped_count} already gone"
        )

    return success


def delete_tenant(nb: pynautobot.api, tenant_uuid: str, dry_run: bool = True) -> bool:
    """Delete the tenant itself. Returns True if successful."""
    try:
        tenant = nb.tenancy.tenants.get(tenant_uuid)
        if not tenant:
            print(f"Tenant {tenant_uuid} not found", file=sys.stderr)
            return False

        if dry_run:
            print(f"[DRY RUN] Would delete tenant: {tenant.name} ({tenant.id})")
        else:
            tenant.delete()
            print(f"Deleted tenant: {tenant.name} ({tenant.id})")

        return True
    except Exception as e:
        print(f"Error deleting tenant {tenant_uuid}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Clean up storage-related objects in Nautobot for a specific tenant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 123e4567-e89b-12d3-a456-426614174000
  %(prog)s 123e4567-e89b-12d3-a456-426614174000 --really-delete
        """,
    )

    parser.add_argument(
        "tenant_uuid", type=validate_uuid, help="UUID of the tenant to clean up"
    )

    parser.add_argument(
        "--really-delete",
        action="store_true",
        help="Actually perform deletions (default is dry-run mode)",
    )

    args = parser.parse_args()

    # Initialize Nautobot connection
    try:
        nb = pynautobot.api(
            url=os.getenv("NAUTOBOT_URL"),
            token=os.getenv("NAUTOBOT_TOKEN"),
        )
    except Exception as e:
        print(f"Error connecting to Nautobot: {e}", file=sys.stderr)
        print(
            "Make sure NAUTOBOT_URL and NAUTOBOT_TOKEN environment variables are set",
            file=sys.stderr,
        )
        sys.exit(1)

    dry_run = not args.really_delete

    if dry_run:
        print("=== DRY RUN MODE ===")
        print("Use --really-delete to actually perform deletions")
        print()
    else:
        print("=== DELETION MODE ===")
        print("This will permanently delete objects!")
        print()

    # Get all objects to delete
    objects = get_objects_to_delete(nb, args.tenant_uuid)

    # Check if tenant exists
    try:
        tenant = nb.tenancy.tenants.get(args.tenant_uuid)
        if not tenant:
            print(f"Tenant {args.tenant_uuid} not found", file=sys.stderr)
            sys.exit(1)
        print(f"Target tenant: {tenant.name} ({tenant.id})")
        print()
    except Exception as e:
        print(f"Error checking tenant {args.tenant_uuid}: {e}", file=sys.stderr)
        sys.exit(1)

    # Print summary of what will be deleted
    print_objects_summary(objects, args.tenant_uuid)

    # Check if there's anything to delete
    total_objects = sum(len(obj_list) for obj_list in objects.values())
    if total_objects == 0:
        print("No objects found to delete for this tenant.")
        if dry_run:
            print("[DRY RUN] Would delete tenant (if it exists)")
        else:
            delete_tenant(nb, args.tenant_uuid, dry_run)
        return

    # Confirm deletion if not in dry-run mode
    if not dry_run:
        response = input(
            f"Are you sure you want to delete {total_objects} objects and the tenant? (yes/no): "
        )
        if response.lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    # Delete objects
    deletion_success = delete_objects(nb, objects, dry_run)

    if deletion_success:
        print("\nObject deletion completed successfully")
    else:
        print("\nObject deletion completed with some errors")

    # Delete tenant regardless of object deletion status (some errors might be expected)
    if delete_tenant(nb, args.tenant_uuid, dry_run):
        print("Tenant deletion completed successfully")
    else:
        print("Failed to delete tenant", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("\n=== DRY RUN COMPLETED ===")
        print("No actual changes were made. Use --really-delete to perform deletions.")


if __name__ == "__main__":
    main()
