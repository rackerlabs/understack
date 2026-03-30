package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/extras"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/ipam"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/tenancy"
	"github.com/samber/lo"
	"go.yaml.in/yaml/v3"
)

type VlanSync struct {
	client         *client.NautobotClient
	vlanSvc        *ipam.VlanService
	vlanGroupSvc   *ipam.VlanGroupService
	locationSvc    *dcim.LocationService
	statusSvc      *dcim.StatusService
	roleSvc        *extras.RoleService
	tenantSvc      *tenancy.TenantService
	tenantGroupSvc *tenancy.TenantGroupService
	tagSvc         *extras.TagService
}

func NewVlanSync(nautobotClient *client.NautobotClient) *VlanSync {
	return &VlanSync{
		client:         nautobotClient.GetClient(),
		vlanSvc:        ipam.NewVlanService(nautobotClient),
		vlanGroupSvc:   ipam.NewVlanGroupService(nautobotClient),
		locationSvc:    dcim.NewLocationService(nautobotClient.GetClient()),
		statusSvc:      dcim.NewStatusService(nautobotClient.GetClient()),
		roleSvc:        extras.NewRoleService(nautobotClient),
		tenantSvc:      tenancy.NewTenantService(nautobotClient),
		tenantGroupSvc: tenancy.NewTenantGroupService(nautobotClient),
		tagSvc:         extras.NewTagService(nautobotClient),
	}
}

func (s *VlanSync) SyncAll(ctx context.Context, data map[string]string) error {
	var vlans models.Vlans
	for key, f := range data {
		var yml []models.Vlan
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		vlans.Vlan = append(vlans.Vlan, yml...)
	}

	for _, vlan := range vlans.Vlan {
		if err := s.syncSingleVlan(ctx, vlan); err != nil {
			return err
		}
	}
	s.deleteObsoleteVlans(ctx, vlans)

	return nil
}

// syncSingleVlan handles the create/update logic for a single VLAN
func (s *VlanSync) syncSingleVlan(ctx context.Context, vlan models.Vlan) error {
	existingVlan := s.vlanSvc.GetByName(ctx, vlan.Name)

	// Build status reference (required)
	statusRef, err := s.buildStatusReference(ctx, vlan.Status)
	if err != nil {
		return fmt.Errorf("failed to build status reference for vlan %s: %w", vlan.Name, err)
	}

	vlanRequest := nb.VLANRequest{
		Vid:    int32(vlan.Vid),
		Name:   vlan.Name,
		Status: statusRef,
	}

	if vlan.Description != "" {
		vlanRequest.Description = nb.PtrString(vlan.Description)
	}

	if vlan.Role != "" {
		roleRef, err := s.buildRoleReference(ctx, vlan.Role)
		if err != nil {
			return fmt.Errorf("failed to build role reference for vlan %s: %w", vlan.Name, err)
		}
		vlanRequest.Role = roleRef
	}

	if len(vlan.Locations) > 0 {
		locationRef, err := s.buildLocationReference(ctx, vlan.Locations[0])
		if err != nil {
			return fmt.Errorf("failed to build location reference for vlan %s: %w", vlan.Name, err)
		}
		vlanRequest.Location = locationRef
	}

	if vlan.VlanGroup != "" {
		vlanRequest.VlanGroup = s.buildVlanGroupReference(ctx, vlan.VlanGroup)
	}

	if vlan.Tenant != "" {
		vlanRequest.Tenant = s.buildTenantReference(ctx, vlan.Tenant)
	}

	customFields := make(map[string]interface{})
	if vlan.TenantGroup != "" {
		customFields["tenant_group"] = s.buildTenantGroupID(ctx, vlan.TenantGroup)
	}
	if len(vlan.DynamicGroups) > 0 {
		customFields["dynamic_groups"] = s.buildDynamicGroupNames(vlan.DynamicGroups)
	}
	if len(vlan.Locations) > 1 {
		customFields["locations"] = s.buildLocationIDs(ctx, vlan.Locations[1:])
	}
	if len(customFields) > 0 {
		vlanRequest.CustomFields = customFields
	}

	if len(vlan.Tags) > 0 {
		vlanRequest.Tags = s.buildTagReferences(ctx, vlan.Tags)
	}

	if existingVlan.Id == nil {
		return s.createVlan(ctx, vlanRequest)
	}

	if !helpers.CompareJSONFields(existingVlan, vlanRequest) {
		return s.updateVlan(ctx, *existingVlan.Id, vlanRequest)
	}

	log.Info("vlan unchanged, skipping update", "name", vlanRequest.Name)
	return nil
}

// createVlan creates a new VLAN in Nautobot
func (s *VlanSync) createVlan(ctx context.Context, request nb.VLANRequest) error {
	createdVlan, err := s.vlanSvc.Create(ctx, request)
	if err != nil || createdVlan == nil {
		return fmt.Errorf("failed to create vlan %s: %w", request.Name, err)
	}
	log.Info("vlan created", "name", request.Name)
	return nil
}

// updateVlan updates an existing VLAN in Nautobot
func (s *VlanSync) updateVlan(ctx context.Context, id string, request nb.VLANRequest) error {
	updatedVlan, err := s.vlanSvc.Update(ctx, id, request)
	if err != nil || updatedVlan == nil {
		return fmt.Errorf("failed to update vlan %s: %w", request.Name, err)
	}
	log.Info("vlan updated", "name", request.Name)
	return nil
}

// deleteObsoleteVlans removes VLANs that are not defined in YAML
func (s *VlanSync) deleteObsoleteVlans(ctx context.Context, vlans models.Vlans) {
	desiredVlans := make(map[string]models.Vlan)
	for _, vlan := range vlans.Vlan {
		desiredVlans[vlan.Name] = vlan
	}

	existingVlans := s.vlanSvc.ListAll(ctx)
	existingMap := make(map[string]nb.VLAN, len(existingVlans))
	for _, vlan := range existingVlans {
		existingMap[vlan.Name] = vlan
	}

	obsoleteVlans := lo.OmitByKeys(existingMap, lo.Keys(desiredVlans))
	for _, vlan := range obsoleteVlans {
		if vlan.Id != nil {
			_ = s.vlanSvc.Destroy(ctx, *vlan.Id)
		}
	}
}

func (s *VlanSync) buildStatusReference(ctx context.Context, name string) (nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	status := s.statusSvc.GetByName(ctx, name)
	if status.Id == nil {
		return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{}, fmt.Errorf("status '%s' not found in Nautobot", name)
	}
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*status.Id), nil
}

func (s *VlanSync) buildRoleReference(ctx context.Context, name string) (nb.NullableApprovalWorkflowUser, error) {
	role := s.roleSvc.GetByName(ctx, name)
	if role.Id == nil {
		return nb.NullableApprovalWorkflowUser{}, fmt.Errorf("role '%s' not found in Nautobot", name)
	}
	return helpers.BuildNullableApprovalWorkflowUser(*role.Id), nil
}

func (s *VlanSync) buildLocationReference(ctx context.Context, name string) (nb.NullableBulkWritablePrefixRequestLocation, error) {
	location := s.locationSvc.GetByName(ctx, name)
	if location.Id == nil {
		return nb.NullableBulkWritablePrefixRequestLocation{}, fmt.Errorf("location '%s' not found in Nautobot", name)
	}
	return helpers.BuildNullableBulkWritablePrefixRequestLocation(*location.Id), nil
}

func (s *VlanSync) buildVlanGroupReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	vlanGroup := s.vlanGroupSvc.GetByName(ctx, name)
	if vlanGroup.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*vlanGroup.Id)
}

func (s *VlanSync) buildTenantReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	tenant := s.tenantSvc.GetByName(ctx, name)
	if tenant.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*tenant.Id)
}

func (s *VlanSync) buildTenantGroupID(ctx context.Context, name string) string {
	tg := s.tenantGroupSvc.GetByName(ctx, name)
	if tg.Id == nil {
		return ""
	}
	return *tg.Id
}

func (s *VlanSync) buildDynamicGroupNames(names []string) []string {
	return names
}

func (s *VlanSync) buildLocationIDs(ctx context.Context, names []string) []string {
	var ids []string
	for _, name := range names {
		location := s.locationSvc.GetByName(ctx, name)
		if location.Id != nil {
			ids = append(ids, *location.Id)
		}
	}
	return ids
}

func (s *VlanSync) buildTagReferences(ctx context.Context, tagNames []string) []nb.ApprovalWorkflowStageResponseApprovalWorkflowStage {
	var tags []nb.ApprovalWorkflowStageResponseApprovalWorkflowStage
	for _, name := range tagNames {
		tag := s.tagSvc.GetByName(ctx, name)
		if tag.Id != nil {
			tags = append(tags, helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*tag.Id))
		}
	}
	return tags
}
