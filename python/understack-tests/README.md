# Integration tests

## Initial setup

Create a file describing how to reach the environment to test.
Generally, the easiest way is to create an .env file similar to the one in `python/understack-tests/example.env`:

```env
OS_AUTH_URL=https://keystone.dev.undercloud.rackspace.net/v3
OS_USERNAME=your-rally-user
OS_PASSWORD=testpassword
OS_TENANT_NAME=your-rally
OS_PROJECT_NAME=your-rally
OS_REGION_NAME=RegionOne
OS_INTERFACE=public
OS_IDENTITY_API_VERSION=3
```

For purpose of the example, save it as `dev.env`. This is for local testing,
for CI it can be more complicated - you could retrieve the credentials from
secrets, passwordsafe, etc. Long story short, they need to be passed down to
the testing container as environment variables.

## Usage

```shell
docker run --rm --env-file dev.env ghcr.io/rackerlabs/understack/understack-tests run-scenario build_a_single_server_with_network.yaml
```

### Available scenarios

- **`build_a_single_server_with_network.yaml`** - boots a simple Ubuntu GP2.SMALL
  server with a plain networking setup. The network is automatically created
  and removed.
- **`floating_ips.yaml`** - build a network, server, router and associate and
  dissociate floating IP
- **`create_tenants.yaml`** - creates and deletes 1000 tenants/projects.

## Listing available scenario plugins

```
docker run --rm ghcr.io/rackerlabs/understack/understack-tests rally plugin list --plugin-base Scenario
```

| Plugin base | Name                                                           | Platform  | Title                                                                |
|-- | -- | -- | -- |
| Scenario    | Authenticate.keystone                                          | openstack | Check Keystone Client.                                               |
| Scenario    | Authenticate.validate_ceilometer                               | openstack | Check Ceilometer Client to ensure validation of token.               |
| Scenario    | Authenticate.validate_cinder                                   | openstack | Check Cinder Client to ensure validation of token.                   |
| Scenario    | Authenticate.validate_glance                                   | openstack | Check Glance Client to ensure validation of token.                   |
| Scenario    | Authenticate.validate_heat                                     | openstack | Check Heat Client to ensure validation of token.                     |
| Scenario    | Authenticate.validate_monasca                                  | openstack | Check Monasca Client to ensure validation of token.                  |
| Scenario    | Authenticate.validate_neutron                                  | openstack | Check Neutron Client to ensure validation of token.                  |
| Scenario    | Authenticate.validate_nova                                     | openstack | Check Nova Client to ensure validation of token.                     |
| Scenario    | Authenticate.validate_octavia                                  | openstack | Check Octavia Client to ensure validation of token.                  |
| Scenario    | BarbicanContainers.create_and_add                              | openstack | Create secret, create generic container, and delete container.       |
| Scenario    | BarbicanContainers.create_and_delete                           | openstack | Create and delete generic container.                                 |
| Scenario    | BarbicanContainers.create_certificate_and_delete               | openstack | Create and delete certificate container.                             |
| Scenario    | BarbicanContainers.create_rsa_and_delete                       | openstack | Create and delete certificate container.                             |
| Scenario    | BarbicanContainers.list                                        | openstack | List Containers.                                                     |
| Scenario    | BarbicanOrders.create_asymmetric_and_delete                    | openstack | Create and delete asymmetric order.                                  |
| Scenario    | BarbicanOrders.create_certificate_and_delete                   | openstack | Create and delete certificate orders                                 |
| Scenario    | BarbicanOrders.create_key_and_delete                           | openstack | Create and delete key orders                                         |
| Scenario    | BarbicanOrders.list                                            | openstack | List Orders.                                                         |
| Scenario    | BarbicanSecrets.create                                         | openstack | Create secret.                                                       |
| Scenario    | BarbicanSecrets.create_and_delete                              | openstack | Create and Delete secret.                                            |
| Scenario    | BarbicanSecrets.create_and_get                                 | openstack | Create and Get Secret.                                               |
| Scenario    | BarbicanSecrets.create_and_list                                | openstack | Create and then list all secrets.                                    |
| Scenario    | BarbicanSecrets.create_symmetric_and_delete                    | openstack | Create and delete symmetric secret                                   |
| Scenario    | BarbicanSecrets.get                                            | openstack | Create and Get Secret.                                               |
| Scenario    | BarbicanSecrets.list                                           | openstack | List secrets.                                                        |
| Scenario    | CinderQos.create_and_get_qos                                   | openstack | Create a qos, then get details of the qos.                           |
| Scenario    | CinderQos.create_and_list_qos                                  | openstack | Create a qos, then list all qos.                                     |
| Scenario    | CinderQos.create_and_set_qos                                   | openstack | Create a qos, then Add/Update keys in qos specs.                     |
| Scenario    | CinderQos.create_qos_associate_and_disassociate_type           | openstack | Create a qos, Associate and Disassociate the qos from volume type.   |
| Scenario    | CinderVolumeBackups.create_incremental_volume_backup           | openstack | Create an incremental volume backup.                                 |
| Scenario    | CinderVolumeTypes.create_and_delete_encryption_type            | openstack | Create and delete encryption type                                    |
| Scenario    | CinderVolumeTypes.create_and_delete_volume_type                | openstack | Create and delete a volume Type.                                     |
| Scenario    | CinderVolumeTypes.create_and_get_volume_type                   | openstack | Create a volume Type, then get the details of the type.              |
| Scenario    | CinderVolumeTypes.create_and_list_encryption_type              | openstack | Create and list encryption type                                      |
| Scenario    | CinderVolumeTypes.create_and_list_volume_types                 | openstack | Create a volume Type, then list all types.                           |
| Scenario    | CinderVolumeTypes.create_and_set_volume_type_keys              | openstack | Create and set a volume type's extra specs.                          |
| Scenario    | CinderVolumeTypes.create_and_update_encryption_type            | openstack | Create and update encryption type                                    |
| Scenario    | CinderVolumeTypes.create_and_update_volume_type                | openstack | create a volume type, then update the type.                          |
| Scenario    | CinderVolumeTypes.create_get_and_delete_encryption_type        | openstack | Create get and delete an encryption type                             |
| Scenario    | CinderVolumeTypes.create_volume_type_add_and_list_type_access  | openstack | Add and list volume type access for the given project.               |
| Scenario    | CinderVolumeTypes.create_volume_type_and_encryption_type       | openstack | Create encryption type                                               |
| Scenario    | CinderVolumes.create_and_accept_transfer                       | openstack | Create a volume transfer, then accept it                             |
| Scenario    | CinderVolumes.create_and_attach_volume                         | openstack | Create a VM and attach a volume to it.                               |
| Scenario    | CinderVolumes.create_and_delete_snapshot                       | openstack | Create and then delete a volume-snapshot.                            |
| Scenario    | CinderVolumes.create_and_delete_volume                         | openstack | Create and then delete a volume.                                     |
| Scenario    | CinderVolumes.create_and_extend_volume                         | openstack | Create and extend a volume and then delete it.                       |
| Scenario    | CinderVolumes.create_and_get_volume                            | openstack | Create a volume and get the volume.                                  |
| Scenario    | CinderVolumes.create_and_list_snapshots                        | openstack | Create and then list a volume-snapshot.                              |
| Scenario    | CinderVolumes.create_and_list_volume                           | openstack | Create a volume and list all volumes.                                |
| Scenario    | CinderVolumes.create_and_list_volume_backups                   | openstack | Create and then list a volume backup.                                |
| Scenario    | CinderVolumes.create_and_restore_volume_backup                 | openstack | Restore volume backup.                                               |
| Scenario    | CinderVolumes.create_and_update_volume                         | openstack | Create a volume and update its name and description.                 |
| Scenario    | CinderVolumes.create_and_upload_volume_to_image                | openstack | Create and upload a volume to image.                                 |
| Scenario    | CinderVolumes.create_from_volume_and_delete_volume             | openstack | Create volume from volume and then delete it.                        |
| Scenario    | CinderVolumes.create_nested_snapshots_and_attach_volume        | openstack | Create a volume from snapshot and attach/detach the volume           |
| Scenario    | CinderVolumes.create_snapshot_and_attach_volume                | openstack | Create vm, volume, snapshot and attach/detach volume.                |
| Scenario    | CinderVolumes.create_volume                                    | openstack | Create a volume.                                                     |
| Scenario    | CinderVolumes.create_volume_and_clone                          | openstack | Create a volume, then clone it to another volume.                    |
| Scenario    | CinderVolumes.create_volume_and_update_readonly_flag           | openstack | Create a volume and then update its readonly flag.                   |
| Scenario    | CinderVolumes.create_volume_backup                             | openstack | Create a volume backup.                                              |
| Scenario    | CinderVolumes.create_volume_from_snapshot                      | openstack | Create a volume-snapshot, then create a volume from this snapshot.   |
| Scenario    | CinderVolumes.list_transfers                                   | openstack | List all transfers.                                                  |
| Scenario    | CinderVolumes.list_types                                       | openstack | List all volume types.                                               |
| Scenario    | CinderVolumes.list_volumes                                     | openstack | List all volumes.                                                    |
| Scenario    | CinderVolumes.modify_volume_metadata                           | openstack | Modify a volume's metadata.                                          |
| Scenario    | DesignateBasic.create_and_delete_recordsets                    | openstack | Create and then delete recordsets.                                   |
| Scenario    | DesignateBasic.create_and_delete_zone                          | openstack | Create and then delete a zone.                                       |
| Scenario    | DesignateBasic.create_and_list_recordsets                      | openstack | Create and then list recordsets.                                     |
| Scenario    | DesignateBasic.create_and_list_zones                           | openstack | Create a zone and list all zones.                                    |
| Scenario    | DesignateBasic.list_recordsets                                 | openstack | List Designate recordsets.                                           |
| Scenario    | DesignateBasic.list_zones                                      | openstack | List Designate zones.                                                |
| Scenario    | Dummy.dummy                                                    | default   | Do nothing and sleep for the given number of seconds (0 by default). |
| Scenario    | Dummy.dummy_exception                                          | default   | Throws an exception.                                                 |
| Scenario    | Dummy.dummy_exception_probability                              | default   | Throws an exception with given probability.                          |
| Scenario    | Dummy.dummy_output                                             | default   | Generate dummy output.                                               |
| Scenario    | Dummy.dummy_random_action                                      | default   | Sleep random time in dummy actions.                                  |
| Scenario    | Dummy.dummy_random_fail_in_atomic                              | default   | Dummy.dummy_random_fail_in_atomic in dummy actions.                  |
| Scenario    | Dummy.dummy_timed_atomic_actions                               | default   | Run some sleepy atomic actions for SLA atomic action tests.          |
| Scenario    | Dummy.failure                                                  | default   | Raise errors in some iterations.                                     |
| Scenario    | Dummy.openstack                                                | openstack | Do nothing and sleep for the given number of seconds (0 by default). |
| Scenario    | ElasticsearchLogging.log_instance                              | openstack | Create nova instance and check it indexed in elasticsearch.          |
| Scenario    | GlanceImages.create_and_deactivate_image                       | openstack | Create an image, then deactivate it.                                 |
| Scenario    | GlanceImages.create_and_delete_image                           | openstack | Create and then delete an image.                                     |
| Scenario    | GlanceImages.create_and_download_image                         | openstack | Create an image, then download data of the image.                    |
| Scenario    | GlanceImages.create_and_get_image                              | openstack | Create and get detailed information of an image.                     |
| Scenario    | GlanceImages.create_and_list_image                             | openstack | Create an image and then list all images.                            |
| Scenario    | GlanceImages.create_and_update_image                           | openstack | Create an image then update it.                                      |
| Scenario    | GlanceImages.create_image_and_boot_instances                   | openstack | Create an image and boot several instances from it.                  |
| Scenario    | GlanceImages.list_images                                       | openstack | List all images.                                                     |
| Scenario    | Gnocchi.get_status                                             | openstack | Get the status of measurements processing.                           |
| Scenario    | Gnocchi.list_capabilities                                      | openstack | List supported aggregation methods.                                  |
| Scenario    | GnocchiArchivePolicy.create_archive_policy                     | openstack | Create archive policy.                                               |
| Scenario    | GnocchiArchivePolicy.create_delete_archive_policy              | openstack | Create archive policy and then delete it.                            |
| Scenario    | GnocchiArchivePolicy.list_archive_policy                       | openstack | List archive policies.                                               |
| Scenario    | GnocchiArchivePolicyRule.create_archive_policy_rule            | openstack | Create archive policy rule.                                          |
| Scenario    | GnocchiArchivePolicyRule.create_delete_archive_policy_rule     | openstack | Create archive policy rule and then delete it.                       |
| Scenario    | GnocchiArchivePolicyRule.list_archive_policy_rule              | openstack | List archive policy rules.                                           |
| Scenario    | GnocchiMetric.create_delete_metric                             | openstack | Create metric and then delete it.                                    |
| Scenario    | GnocchiMetric.create_metric                                    | openstack | Create metric.                                                       |
| Scenario    | GnocchiMetric.list_metric                                      | openstack | List metrics.                                                        |
| Scenario    | GnocchiResource.create_delete_resource                         | openstack | Create resource and then delete it.                                  |
| Scenario    | GnocchiResource.create_resource                                | openstack | Create resource.                                                     |
| Scenario    | GnocchiResourceType.create_delete_resource_type                | openstack | Create resource type and then delete it.                             |
| Scenario    | GnocchiResourceType.create_resource_type                       | openstack | Create resource type.                                                |
| Scenario    | GnocchiResourceType.list_resource_type                         | openstack | List resource types.                                                 |
| Scenario    | GrafanaMetrics.push_metric_from_instance                       | openstack | Create nova instance with pushing metric script as userdata.         |
| Scenario    | GrafanaMetrics.push_metric_locally                             | openstack | Push random metric to Pushgateway locally and check it in Grafana.   |
| Scenario    | HeatStacks.create_and_delete_stack                             | openstack | Create and then delete a stack.                                      |
| Scenario    | HeatStacks.create_and_list_stack                               | openstack | Create a stack and then list all stacks.                             |
| Scenario    | HeatStacks.create_check_delete_stack                           | openstack | Create, check and delete a stack.                                    |
| Scenario    | HeatStacks.create_snapshot_restore_delete_stack                | openstack | Create, snapshot-restore and then delete a stack.                    |
| Scenario    | HeatStacks.create_stack_and_list_output                        | openstack | Create stack and list outputs by using new algorithm.                |
| Scenario    | HeatStacks.create_stack_and_list_output_via_API                | openstack | Create stack and list outputs by using old algorithm.                |
| Scenario    | HeatStacks.create_stack_and_scale                              | openstack | Create an autoscaling stack and invoke a scaling policy.             |
| Scenario    | HeatStacks.create_stack_and_show_output                        | openstack | Create stack and show output by using new algorithm.                 |
| Scenario    | HeatStacks.create_stack_and_show_output_via_API                | openstack | Create stack and show output by using old algorithm.                 |
| Scenario    | HeatStacks.create_suspend_resume_delete_stack                  | openstack | Create, suspend-resume and then delete a stack.                      |
| Scenario    | HeatStacks.create_update_delete_stack                          | openstack | Create, update and then delete a stack.                              |
| Scenario    | HeatStacks.list_stacks_and_events                              | openstack | List events from tenant stacks.                                      |
| Scenario    | HeatStacks.list_stacks_and_resources                           | openstack | List all resources from tenant stacks.                               |
| Scenario    | HttpRequests.check_random_request                              | default   | Executes random HTTP requests from provided list.                    |
| Scenario    | HttpRequests.check_request                                     | default   | Standard way for testing web services using HTTP requests.           |
| Scenario    | IronicNodes.create_and_delete_node                             | openstack | Create and delete node.                                              |
| Scenario    | IronicNodes.create_and_list_node                               | openstack | Create and list nodes.                                               |
| Scenario    | K8sPods.create_pods                                            | openstack | create pods and wait for them to be ready.                           |
| Scenario    | K8sPods.create_rcs                                             | openstack | create rcs and wait for them to be ready.                            |
| Scenario    | K8sPods.list_pods                                              | openstack | List all pods.                                                       |
| Scenario    | KeystoneBasic.add_and_remove_user_role                         | openstack | Create a user role add to a user and disassociate.                   |
| Scenario    | KeystoneBasic.authenticate_user_and_validate_token             | openstack | Authenticate and validate a keystone token.                          |
| Scenario    | KeystoneBasic.create_add_and_list_user_roles                   | openstack | Create user role, add it and list user roles for given user.         |
| Scenario    | KeystoneBasic.create_and_delete_ec2credential                  | openstack | Create and delete keystone ec2-credential.                           |
| Scenario    | KeystoneBasic.create_and_delete_role                           | openstack | Create a user role and delete it.                                    |
| Scenario    | KeystoneBasic.create_and_delete_service                        | openstack | Create and delete service.                                           |
| Scenario    | KeystoneBasic.create_and_get_role                              | openstack | Create a user role and get it detailed information.                  |
| Scenario    | KeystoneBasic.create_and_list_ec2credentials                   | openstack | Create and List all keystone ec2-credentials.                        |
| Scenario    | KeystoneBasic.create_and_list_roles                            | openstack | Create a role, then list all roles.                                  |
| Scenario    | KeystoneBasic.create_and_list_services                         | openstack | Create and list services.                                            |
| Scenario    | KeystoneBasic.create_and_list_tenants                          | openstack | Create a keystone tenant with random name and list all tenants.      |
| Scenario    | KeystoneBasic.create_and_list_users                            | openstack | Create a keystone user with random name and list all users.          |
| Scenario    | KeystoneBasic.create_and_update_user                           | openstack | Create user and update the user.                                     |
| Scenario    | KeystoneBasic.create_delete_user                               | openstack | Create a keystone user with random name and then delete it.          |
| Scenario    | KeystoneBasic.create_tenant                                    | openstack | Create a keystone tenant with random name.                           |
| Scenario    | KeystoneBasic.create_tenant_with_users                         | openstack | Create a keystone tenant and several users belonging to it.          |
| Scenario    | KeystoneBasic.create_update_and_delete_tenant                  | openstack | Create, update and delete tenant.                                    |
| Scenario    | KeystoneBasic.create_user                                      | openstack | Create a keystone user with random name.                             |
| Scenario    | KeystoneBasic.create_user_set_enabled_and_delete               | openstack | Create a keystone user, enable or disable it, and delete it.         |
| Scenario    | KeystoneBasic.create_user_update_password                      | openstack | Create user and update password for that user.                       |
| Scenario    | KeystoneBasic.get_entities                                     | openstack | Get instance of a tenant, user, role and service by id's.            |
| Scenario    | MagnumClusterTemplates.list_cluster_templates                  | openstack | List all cluster_templates.                                          |
| Scenario    | MagnumClusters.create_and_list_clusters                        | openstack | create cluster and then list all clusters.                           |
| Scenario    | MagnumClusters.list_clusters                                   | openstack | List all clusters.                                                   |
| Scenario    | ManilaShares.attach_security_service_to_share_network          | openstack | Attaches security service to share network.                          |
| Scenario    | ManilaShares.create_and_delete_share                           | openstack | Create and delete a share.                                           |
| Scenario    | ManilaShares.create_and_extend_share                           | openstack | Create and extend a share                                            |
| Scenario    | ManilaShares.create_and_list_share                             | openstack | Create a share and list all shares.                                  |
| Scenario    | ManilaShares.create_and_shrink_share                           | openstack | Create and shrink a share                                            |
| Scenario    | ManilaShares.create_security_service_and_delete                | openstack | Creates security service and then deletes.                           |
| Scenario    | ManilaShares.create_share_and_access_from_vm                   | openstack | Create a share and access it from a VM.                              |
| Scenario    | ManilaShares.create_share_network_and_delete                   | openstack | Creates share network and then deletes.                              |
| Scenario    | ManilaShares.create_share_network_and_list                     | openstack | Creates share network and then lists it.                             |
| Scenario    | ManilaShares.create_share_then_allow_and_deny_access           | openstack | Create a share and allow and deny access to it                       |
| Scenario    | ManilaShares.list_share_servers                                | openstack | Lists share servers.                                                 |
| Scenario    | ManilaShares.list_shares                                       | openstack | Basic scenario for 'share list' operation.                           |
| Scenario    | ManilaShares.set_and_delete_metadata                           | openstack | Sets and deletes share metadata.                                     |
| Scenario    | MistralExecutions.create_execution_from_workbook               | openstack | Scenario tests execution creation and deletion.                      |
| Scenario    | MistralExecutions.list_executions                              | openstack | Scenario test mistral execution-list command.                        |
| Scenario    | MistralWorkbooks.create_workbook                               | openstack | Scenario tests workbook creation and deletion.                       |
| Scenario    | MistralWorkbooks.list_workbooks                                | openstack | Scenario test mistral workbook-list command.                         |
| Scenario    | MonascaMetrics.list_metrics                                    | openstack | Fetch user's metrics.                                                |
| Scenario    | MuranoEnvironments.create_and_delete_environment               | openstack | Create environment, session and delete environment.                  |
| Scenario    | MuranoEnvironments.create_and_deploy_environment               | openstack | Create environment, session and deploy environment.                  |
| Scenario    | MuranoEnvironments.list_environments                           | openstack | List the murano environments.                                        |
| Scenario    | MuranoPackages.import_and_delete_package                       | openstack | Import Murano package and then delete it.                            |
| Scenario    | MuranoPackages.import_and_filter_applications                  | openstack | Import Murano package and then filter packages by some criteria.     |
| Scenario    | MuranoPackages.import_and_list_packages                        | openstack | Import Murano package and get list of packages.                      |
| Scenario    | MuranoPackages.package_lifecycle                               | openstack | Import Murano package, modify it and then delete it.                 |
| Scenario    | NeutronBGPVPN.create_and_delete_bgpvpns                        | openstack | Create bgpvpn and delete the bgpvpn.                                 |
| Scenario    | NeutronBGPVPN.create_and_list_bgpvpns                          | openstack | Create a bgpvpn and then list all bgpvpns                            |
| Scenario    | NeutronBGPVPN.create_and_list_networks_associations            | openstack | Associate a network and list networks associations.                  |
| Scenario    | NeutronBGPVPN.create_and_list_routers_associations             | openstack | Associate a router and list routers associations.                    |
| Scenario    | NeutronBGPVPN.create_and_update_bgpvpns                        | openstack | Create and Update bgpvpns                                            |
| Scenario    | NeutronBGPVPN.create_bgpvpn_assoc_disassoc_networks            | openstack | Associate a network and disassociate it from a BGP VPN.              |
| Scenario    | NeutronBGPVPN.create_bgpvpn_assoc_disassoc_routers             | openstack | Associate a router and disassociate it from a BGP VPN.               |
| Scenario    | NeutronLoadbalancerV1.create_and_delete_healthmonitors         | openstack | Create a healthmonitor(v1) and delete healthmonitors(v1).            |
| Scenario    | NeutronLoadbalancerV1.create_and_delete_pools                  | openstack | Create pools(v1) and delete pools(v1).                               |
| Scenario    | NeutronLoadbalancerV1.create_and_delete_vips                   | openstack | Create a vip(v1) and then delete vips(v1).                           |
| Scenario    | NeutronLoadbalancerV1.create_and_list_healthmonitors           | openstack | Create healthmonitors(v1) and list healthmonitors(v1).               |
| Scenario    | NeutronLoadbalancerV1.create_and_list_pools                    | openstack | Create a pool(v1) and then list pools(v1).                           |
| Scenario    | NeutronLoadbalancerV1.create_and_list_vips                     | openstack | Create a vip(v1) and then list vips(v1).                             |
| Scenario    | NeutronLoadbalancerV1.create_and_update_healthmonitors         | openstack | Create a healthmonitor(v1) and update healthmonitors(v1).            |
| Scenario    | NeutronLoadbalancerV1.create_and_update_pools                  | openstack | Create pools(v1) and update pools(v1).                               |
| Scenario    | NeutronLoadbalancerV1.create_and_update_vips                   | openstack | Create vips(v1) and update vips(v1).                                 |
| Scenario    | NeutronLoadbalancerV2.create_and_list_loadbalancers            | openstack | Create a loadbalancer(v2) and then list loadbalancers(v2).           |
| Scenario    | NeutronNetworks.associate_and_dissociate_floating_ips          | openstack | Associate and dissociate floating IPs.                               |
| Scenario    | NeutronNetworks.create_and_bind_ports                          | openstack | Bind a given number of ports.                                        |
| Scenario    | NeutronNetworks.create_and_delete_floating_ips                 | openstack | Create and delete floating IPs.                                      |
| Scenario    | NeutronNetworks.create_and_delete_networks                     | openstack | Create and delete a network.                                         |
| Scenario    | NeutronNetworks.create_and_delete_ports                        | openstack | Create and delete a port.                                            |
| Scenario    | NeutronNetworks.create_and_delete_routers                      | openstack | Create and delete a given number of routers.                         |
| Scenario    | NeutronNetworks.create_and_delete_subnets                      | openstack | Create and delete a given number of subnets.                         |
| Scenario    | NeutronNetworks.create_and_list_floating_ips                   | openstack | Create and list floating IPs.                                        |
| Scenario    | NeutronNetworks.create_and_list_networks                       | openstack | Create a network and then list all networks.                         |
| Scenario    | NeutronNetworks.create_and_list_ports                          | openstack | Create and a given number of ports and list all ports.               |
| Scenario    | NeutronNetworks.create_and_list_routers                        | openstack | Create and a given number of routers and list all routers.           |
| Scenario    | NeutronNetworks.create_and_list_subnets                        | openstack | Create and a given number of subnets and list all subnets.           |
| Scenario    | NeutronNetworks.create_and_show_network                        | openstack | Create a network and show network details.                           |
| Scenario    | NeutronNetworks.create_and_show_ports                          | openstack | Create a given number of ports and show created ports in turn.       |
| Scenario    | NeutronNetworks.create_and_show_routers                        | openstack | Create and show a given number of routers.                           |
| Scenario    | NeutronNetworks.create_and_show_subnets                        | openstack | Create and show a subnet details.                                    |
| Scenario    | NeutronNetworks.create_and_update_networks                     | openstack | Create and update a network.                                         |
| Scenario    | NeutronNetworks.create_and_update_ports                        | openstack | Create and update a given number of ports.                           |
| Scenario    | NeutronNetworks.create_and_update_routers                      | openstack | Create and update a given number of routers.                         |
| Scenario    | NeutronNetworks.create_and_update_subnets                      | openstack | Create and update a subnet.                                          |
| Scenario    | NeutronNetworks.list_agents                                    | openstack | List all neutron agents.                                             |
| Scenario    | NeutronNetworks.set_and_clear_router_gateway                   | openstack | Set and Remove the external network gateway from a router.           |
| Scenario    | NeutronSecurityGroup.create_and_delete_security_group_rule     | openstack | Create and delete Neutron security-group-rule.                       |
| Scenario    | NeutronSecurityGroup.create_and_delete_security_groups         | openstack | Create and delete Neutron security-groups.                           |
| Scenario    | NeutronSecurityGroup.create_and_list_security_group_rules      | openstack | Create and list Neutron security-group-rules.                        |
| Scenario    | NeutronSecurityGroup.create_and_list_security_groups           | openstack | Create and list Neutron security-groups.                             |
| Scenario    | NeutronSecurityGroup.create_and_show_security_group            | openstack | Create and show Neutron security-group.                              |
| Scenario    | NeutronSecurityGroup.create_and_show_security_group_rule       | openstack | Create and show Neutron security-group-rule.                         |
| Scenario    | NeutronSecurityGroup.create_and_update_security_groups         | openstack | Create and update Neutron security-groups.                           |
| Scenario    | NeutronSubnets.delete_subnets                                  | openstack | Delete a subnet that belongs to each precreated network.             |
| Scenario    | NeutronTrunks.boot_server_and_add_subports                     | openstack | Boot a server and add subports.                                      |
| Scenario    | NeutronTrunks.boot_server_and_batch_add_subports               | openstack | Boot a server and add subports in batches.                           |
| Scenario    | NeutronTrunks.boot_server_with_subports                        | openstack | Boot a server with subports.                                         |
| Scenario    | NeutronTrunks.create_and_list_trunks                           | openstack | Create a given number of trunks with subports and list all trunks.   |
| Scenario    | NovaAggregates.create_aggregate_add_and_remove_host            | openstack | Create an aggregate, add a host to and remove the host from it       |
| Scenario    | NovaAggregates.create_aggregate_add_host_and_boot_server       | openstack | Scenario to create and verify an aggregate                           |
| Scenario    | NovaAggregates.create_and_delete_aggregate                     | openstack | Create an aggregate and then delete it.                              |
| Scenario    | NovaAggregates.create_and_get_aggregate_details                | openstack | Create an aggregate and then get its details.                        |
| Scenario    | NovaAggregates.create_and_list_aggregates                      | openstack | Create a aggregate and then list all aggregates.                     |
| Scenario    | NovaAggregates.create_and_update_aggregate                     | openstack | Create an aggregate and then update its name and availability_zone   |
| Scenario    | NovaAggregates.list_aggregates                                 | openstack | List all nova aggregates.                                            |
| Scenario    | NovaAvailabilityZones.list_availability_zones                  | openstack | List all availability zones.                                         |
| Scenario    | NovaFlavors.create_and_delete_flavor                           | openstack | Create flavor and delete the flavor.                                 |
| Scenario    | NovaFlavors.create_and_get_flavor                              | openstack | Create flavor and get detailed information of the flavor.            |
| Scenario    | NovaFlavors.create_and_list_flavor_access                      | openstack | Create a non-public flavor and list its access rules                 |
| Scenario    | NovaFlavors.create_flavor                                      | openstack | Create a flavor.                                                     |
| Scenario    | NovaFlavors.create_flavor_and_add_tenant_access                | openstack | Create a flavor and Add flavor access for the given tenant.          |
| Scenario    | NovaFlavors.create_flavor_and_set_keys                         | openstack | Create flavor and set keys to the flavor.                            |
| Scenario    | NovaFlavors.list_flavors                                       | openstack | List all flavors.                                                    |
| Scenario    | NovaHypervisors.list_and_get_hypervisors                       | openstack | List and Get hypervisors.                                            |
| Scenario    | NovaHypervisors.list_and_get_uptime_hypervisors                | openstack | List hypervisors,then display the uptime of it.                      |
| Scenario    | NovaHypervisors.list_and_search_hypervisors                    | openstack | List all servers belonging to specific hypervisor.                   |
| Scenario    | NovaHypervisors.list_hypervisors                               | openstack | List hypervisors.                                                    |
| Scenario    | NovaHypervisors.statistics_hypervisors                         | openstack | Get hypervisor statistics over all compute nodes.                    |
| Scenario    | NovaKeypair.boot_and_delete_server_with_keypair                | openstack | Boot and delete server with keypair.                                 |
| Scenario    | NovaKeypair.create_and_delete_keypair                          | openstack | Create a keypair with random name and delete keypair.                |
| Scenario    | NovaKeypair.create_and_get_keypair                             | openstack | Create a keypair and get the keypair details.                        |
| Scenario    | NovaKeypair.create_and_list_keypairs                           | openstack | Create a keypair with random name and list keypairs.                 |
| Scenario    | NovaServerGroups.create_and_delete_server_group                | openstack | Create a server group, then delete it.                               |
| Scenario    | NovaServerGroups.create_and_get_server_group                   | openstack | Create a server group, then get its detailed information.            |
| Scenario    | NovaServerGroups.create_and_list_server_groups                 | openstack | Create a server group, then list all server groups.                  |
| Scenario    | NovaServers.boot_and_associate_floating_ip                     | openstack | Boot a server and associate a floating IP to it.                     |
| Scenario    | NovaServers.boot_and_bounce_server                             | openstack | Boot a server and run specified actions against it.                  |
| Scenario    | NovaServers.boot_and_delete_multiple_servers                   | openstack | Boot multiple servers in a single request and delete them.           |
| Scenario    | NovaServers.boot_and_delete_server                             | openstack | Boot and delete a server.                                            |
| Scenario    | NovaServers.boot_and_get_console_output                        | openstack | Get text console output from server.                                 |
| Scenario    | NovaServers.boot_and_get_console_url                           | openstack | Retrieve a console url of a server.                                  |
| Scenario    | NovaServers.boot_and_list_server                               | openstack | Boot a server from an image and then list all servers.               |
| Scenario    | NovaServers.boot_and_live_migrate_server                       | openstack | Live Migrate a server.                                               |
| Scenario    | NovaServers.boot_and_migrate_server                            | openstack | Migrate a server.                                                    |
| Scenario    | NovaServers.boot_and_rebuild_server                            | openstack | Rebuild a server.                                                    |
| Scenario    | NovaServers.boot_and_show_server                               | openstack | Show server details.                                                 |
| Scenario    | NovaServers.boot_and_update_server                             | openstack | Boot a server, then update its name and description.                 |
| Scenario    | NovaServers.boot_lock_unlock_and_delete                        | openstack | Boot a server, lock it, then unlock and delete it.                   |
| Scenario    | NovaServers.boot_server                                        | openstack | Boot a server.                                                       |
| Scenario    | NovaServers.boot_server_and_attach_interface                   | openstack | Create server and subnet, then attach the interface to it.           |
| Scenario    | NovaServers.boot_server_and_list_interfaces                    | openstack | Boot a server and list interfaces attached to it.                    |
| Scenario    | NovaServers.boot_server_associate_and_dissociate_floating_ip   | openstack | Boot a server associate and dissociate a floating IP from it.        |
| Scenario    | NovaServers.boot_server_attach_created_volume_and_extend       | openstack | Create a VM from image, attach a volume then extend volume           |
| Scenario    | NovaServers.boot_server_attach_created_volume_and_live_migrate | openstack | Create a VM, attach a volume to it and live migrate.                 |
| Scenario    | NovaServers.boot_server_attach_created_volume_and_resize       | openstack | Create a VM from image, attach a volume to it and resize.            |
| Scenario    | NovaServers.boot_server_attach_volume_and_list_attachments     | openstack | Create a VM, attach N volume to it and list server's attachment.     |
| Scenario    | NovaServers.boot_server_from_volume                            | openstack | Boot a server from volume.                                           |
| Scenario    | NovaServers.boot_server_from_volume_and_delete                 | openstack | Boot a server from volume and then delete it.                        |
| Scenario    | NovaServers.boot_server_from_volume_and_live_migrate           | openstack | Boot a server from volume and then migrate it.                       |
| Scenario    | NovaServers.boot_server_from_volume_and_resize                 | openstack | Boot a server from volume, then resize and delete it.                |
| Scenario    | NovaServers.boot_server_from_volume_snapshot                   | openstack | Boot a server from a snapshot.                                       |
| Scenario    | NovaServers.list_servers                                       | openstack | List all servers.                                                    |
| Scenario    | NovaServers.pause_and_unpause_server                           | openstack | Create a server, pause, unpause and then delete it                   |
| Scenario    | NovaServers.resize_server                                      | openstack | Boot a server, then resize and delete it.                            |
| Scenario    | NovaServers.resize_shutoff_server                              | openstack | Boot a server and stop it, then resize and delete it.                |
| Scenario    | NovaServers.shelve_and_unshelve_server                         | openstack | Create a server, shelve, unshelve and then delete it                 |
| Scenario    | NovaServers.snapshot_server                                    | openstack | Boot a server, make its snapshot and delete both.                    |
| Scenario    | NovaServers.suspend_and_resume_server                          | openstack | Create a server, suspend, resume and then delete it                  |
| Scenario    | NovaServices.list_services                                     | openstack | List all nova services.                                              |
| Scenario    | Octavia.create_and_delete_loadbalancers                        | openstack | Create a loadbalancer per each subnet and then delete loadbalancer   |
| Scenario    | Octavia.create_and_delete_pools                                | openstack | Create a pool per each subnet and then delete pool                   |
| Scenario    | Octavia.create_and_list_loadbalancers                          | openstack | Create a loadbalancer per each subnet and then list loadbalancers.   |
| Scenario    | Octavia.create_and_list_pools                                  | openstack | Create a loadbalancer pool per each subnet and then pools.           |
| Scenario    | Octavia.create_and_show_loadbalancers                          | openstack | Create a loadbalancer per each subnet and then compare               |
| Scenario    | Octavia.create_and_show_pools                                  | openstack | Create a pool per each subnet and show it                            |
| Scenario    | Octavia.create_and_stats_loadbalancers                         | openstack | Create a loadbalancer per each subnet and stats                      |
| Scenario    | Octavia.create_and_update_loadbalancers                        | openstack | Create a loadbalancer per each subnet and then update                |
| Scenario    | Octavia.create_and_update_pools                                | openstack | Create a pool per each subnet and then update                        |
| Scenario    | Quotas.cinder_get                                              | openstack | Get quotas for Cinder.                                               |
| Scenario    | Quotas.cinder_update                                           | openstack | Update quotas for Cinder.                                            |
| Scenario    | Quotas.cinder_update_and_delete                                | openstack | Update and Delete quotas for Cinder.                                 |
| Scenario    | Quotas.neutron_update                                          | openstack | Update quotas for neutron.                                           |
| Scenario    | Quotas.nova_get                                                | openstack | Get quotas for nova.                                                 |
| Scenario    | Quotas.nova_update                                             | openstack | Update quotas for Nova.                                              |
| Scenario    | Quotas.nova_update_and_delete                                  | openstack | Update and delete quotas for Nova.                                   |
| Scenario    | SaharaClusters.create_and_delete_cluster                       | openstack | Launch and delete a Sahara Cluster.                                  |
| Scenario    | SaharaClusters.create_scale_delete_cluster                     | openstack | Launch, scale and delete a Sahara Cluster.                           |
| Scenario    | SaharaJob.create_launch_job                                    | openstack | Create and execute a Sahara EDP Job.                                 |
| Scenario    | SaharaJob.create_launch_job_sequence                           | openstack | Create and execute a sequence of the Sahara EDP Jobs.                |
| Scenario    | SaharaJob.create_launch_job_sequence_with_scaling              | openstack | Create and execute Sahara EDP Jobs on a scaling Cluster.             |
| Scenario    | SaharaNodeGroupTemplates.create_and_list_node_group_templates  | openstack | Create and list Sahara Node Group Templates.                         |
| Scenario    | SaharaNodeGroupTemplates.create_delete_node_group_templates    | openstack | Create and delete Sahara Node Group Templates.                       |
| Scenario    | SenlinClusters.create_and_delete_cluster                       | openstack | Create a cluster and then delete it.                                 |
| Scenario    | SwiftObjects.create_container_and_object_then_delete_all       | openstack | Create container and objects then delete everything created.         |
| Scenario    | SwiftObjects.create_container_and_object_then_download_object  | openstack | Create container and objects then download all objects.              |
| Scenario    | SwiftObjects.create_container_and_object_then_list_objects     | openstack | Create container and objects then list all objects.                  |
| Scenario    | SwiftObjects.list_and_download_objects_in_containers           | openstack | List and download objects in all containers.                         |
| Scenario    | SwiftObjects.list_objects_in_containers                        | openstack | List objects in all containers.                                      |
| Scenario    | VMTasks.boot_runcommand_delete                                 | openstack | Boot a server, run script specified in command and delete server.    |
| Scenario    | VMTasks.check_designate_dns_resolving                          | openstack | Try to resolve hostname from VM against existing designate DNS.      |
| Scenario    | VMTasks.dd_load_test                                           | openstack | Boot a server from a custom image and performs dd load test.         |
| Scenario    | VMTasks.runcommand_heat                                        | openstack | Run workload on stack deployed by heat.                              |
| Scenario    | Watcher.create_audit_and_delete                                | openstack | Create and delete audit.                                             |
| Scenario    | Watcher.create_audit_template_and_delete                       | openstack | Create audit template and delete it.                                 |
| Scenario    | Watcher.list_audit_templates                                   | openstack | List existing audit templates.                                       |
| Scenario    | ZaqarBasic.create_queue                                        | openstack | Create a Zaqar queue with a random name.                             |
| Scenario    | ZaqarBasic.producer_consumer                                   | openstack | Serial message producer/consumer.                                    |

Each plugin's documentation can be viewed with

```shell
docker run --rm --env-file dev.env ghcr.io/rackerlabs/understack/understack-tests rally plugin show NovaFlavors.create_flavor
```
