# Ansible

Ansible is used to configure different parts of the overall system
in a consistent manner. To this effect a container is produced with
playbooks, roles and collections pre-installed and it can be run by
providing system configuration to it.

## Execution Environment

Ansible is executed within a container which is build within this repo.
The configuration and the source are contained within the
[`ansible/`][ansible-src] directory.

## Configuration

The execution environment within the container is [ansible-runner][ansible-runner].
An inventory directory is necessary to be provided which would be part
of your system deployment data.

Anything which is rackspace specific will be mounted inside ansible container.

For example ansible hosts file and group-vars which are [deployment specific](https://github.com/RSS-Engineering/undercloud-deploy/tree/main/bravo-uc-iad3-dev/inventory) are created as [config-maps](https://github.com/RSS-Engineering/undercloud-deploy/blob/main/bravo-uc-iad3-dev/manifests/nautobot/kustomization.yaml#L13-L23) and [mounted as volumes](https://github.com/rackerlabs/understack/blob/main/components/keystone/values.yaml#L156-L167)

## Sample Execution

```bash
docker run --rm -it ghcr.io/rackerlabs/understack/ansible:latest -- \
  ansible-runner run /runner --playbook debug.yaml
```

[ansible-src]: <https://github.com/rackerlabs/understack/tree/main/ansible>
[ansible-runner]: <https://ansible.readthedocs.io/projects/runner/en/stable/intro/>
