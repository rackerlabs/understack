package sync

import (
	"context"
	"fmt"
	"time"

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

type PrefixSync struct {
	client         *client.NautobotClient
	prefixSvc      *ipam.PrefixService
	namespaceSvc   *ipam.NamespaceService
	vlanGroupSvc   *ipam.VlanGroupService
	vlanSvc        *ipam.VlanService
	vrfSvc         *ipam.VrfService
	rirSvc         *ipam.RirService
	locationSvc    *dcim.LocationService
	statusSvc      *dcim.StatusService
	roleSvc        *extras.RoleService
	tenantSvc      *tenancy.TenantService
	tenantGroupSvc *tenancy.TenantGroupService
	tagSvc         *extras.TagService
}

func NewPrefixSync(nautobotClient *client.NautobotClient) *PrefixSync {
	return &PrefixSync{
		client:         nautobotClient.GetClient(),
		prefixSvc:      ipam.NewPrefixService(nautobotClient),
		namespaceSvc:   ipam.NewNamespaceService(nautobotClient),
		vlanGroupSvc:   ipam.NewVlanGroupService(nautobotClient),
		vlanSvc:        ipam.NewVlanService(nautobotClient),
		vrfSvc:         ipam.NewVrfService(nautobotClient),
		rirSvc:         ipam.NewRirService(nautobotClient),
		locationSvc:    dcim.NewLocationService(nautobotClient.GetClient()),
		statusSvc:      dcim.NewStatusService(nautobotClient.GetClient()),
		roleSvc:        extras.NewRoleService(nautobotClient),
		tenantSvc:      tenancy.NewTenantService(nautobotClient),
		tenantGroupSvc: tenancy.NewTenantGroupService(nautobotClient),
		tagSvc:         extras.NewTagService(nautobotClient),
	}
}

func (s *PrefixSync) SyncAll(ctx context.Context, data map[string]string) error {
	var prefixes models.Prefixes
	for key, f := range data {
		var yml []models.Prefix
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		prefixes.Prefix = append(prefixes.Prefix, yml...)
	}

	for _, prefix := range prefixes.Prefix {
		if err := s.syncSinglePrefix(ctx, prefix); err != nil {
			return err
		}
	}
	s.deleteObsoletePrefixes(ctx, prefixes)

	return nil
}

// syncSinglePrefix handles the create/update logic for a single prefix
func (s *PrefixSync) syncSinglePrefix(ctx context.Context, prefix models.Prefix) error {
	existingPrefix := s.prefixSvc.GetByPrefix(ctx, prefix.Prefix)

	// Build status reference (required)
	statusRef, err := s.buildStatusReference(ctx, prefix.Status)
	if err != nil {
		return fmt.Errorf("failed to build status reference for prefix %s: %w", prefix.Prefix, err)
	}

	prefixRequest := nb.WritablePrefixRequest{
		Prefix: prefix.Prefix,
		Status: statusRef,
	}

	if prefix.Description != "" {
		prefixRequest.Description = nb.PtrString(prefix.Description)
	}

	if prefix.Type != "" {
		typeChoice := nb.PrefixTypeChoices(prefix.Type)
		prefixRequest.Type = &typeChoice
	}

	if prefix.Namespace != "" {
		nsRef, err := s.buildNamespaceReference(ctx, prefix.Namespace)
		if err != nil {
			return fmt.Errorf("failed to build namespace reference for prefix %s: %w", prefix.Prefix, err)
		}
		prefixRequest.Namespace = nsRef
	}

	if prefix.Role != "" {
		roleRef, err := s.buildRoleReference(ctx, prefix.Role)
		if err != nil {
			return fmt.Errorf("failed to build role reference for prefix %s: %w", prefix.Prefix, err)
		}
		prefixRequest.Role = roleRef
	}

	if prefix.Rir != "" {
		rirRef, err := s.buildRirReference(ctx, prefix.Rir)
		if err != nil {
			return fmt.Errorf("failed to build rir reference for prefix %s: %w", prefix.Prefix, err)
		}
		prefixRequest.Rir = rirRef
	}

	if prefix.DateAllocated != "" {
		dateRef, err := s.parseDateAllocated(prefix.DateAllocated)
		if err != nil {
			return fmt.Errorf("failed to parse date_allocated for prefix %s: %w", prefix.Prefix, err)
		}
		prefixRequest.DateAllocated = *nb.NewNullableTime(&dateRef)
	}

	if len(prefix.Locations) > 0 {
		locationRef, err := s.buildLocationReference(ctx, prefix.Locations[0])
		if err != nil {
			return fmt.Errorf("failed to build location reference for prefix %s: %w", prefix.Prefix, err)
		}
		prefixRequest.Location = locationRef
	}

	if prefix.Vlan != "" {
		prefixRequest.Vlan = s.buildVlanReference(ctx, prefix.Vlan)
	}

	if prefix.Tenant != "" {
		prefixRequest.Tenant = s.buildTenantReference(ctx, prefix.Tenant)
	}

	customFields := make(map[string]interface{})
	if prefix.TenantGroup != "" {
		customFields["tenant_group"] = s.buildTenantGroupID(ctx, prefix.TenantGroup)
	}
	if prefix.VlanGroup != "" {
		customFields["vlan_group"] = s.buildVlanGroupID(ctx, prefix.VlanGroup)
	}
	if len(prefix.Vrfs) > 0 {
		customFields["vrfs"] = s.buildVrfIDs(ctx, prefix.Vrfs)
	}
	if len(prefix.Locations) > 1 {
		customFields["locations"] = s.buildLocationIDs(ctx, prefix.Locations[1:])
	}
	if len(customFields) > 0 {
		prefixRequest.CustomFields = customFields
	}

	if len(prefix.Tags) > 0 {
		prefixRequest.Tags = s.buildTagReferences(ctx, prefix.Tags)
	}

	if existingPrefix.Id == nil {
		return s.createPrefix(ctx, prefixRequest)
	}

	if !helpers.CompareJSONFields(existingPrefix, prefixRequest) {
		return s.updatePrefix(ctx, *existingPrefix.Id, prefixRequest)
	}

	log.Info("prefix unchanged, skipping update", "prefix", prefixRequest.Prefix)
	return nil
}

// createPrefix creates a new prefix in Nautobot
func (s *PrefixSync) createPrefix(ctx context.Context, request nb.WritablePrefixRequest) error {
	createdPrefix, err := s.prefixSvc.Create(ctx, request)
	if err != nil || createdPrefix == nil {
		return fmt.Errorf("failed to create prefix %s: %w", request.Prefix, err)
	}
	log.Info("prefix created", "prefix", request.Prefix)
	return nil
}

// updatePrefix updates an existing prefix in Nautobot
func (s *PrefixSync) updatePrefix(ctx context.Context, id string, request nb.WritablePrefixRequest) error {
	updatedPrefix, err := s.prefixSvc.Update(ctx, id, request)
	if err != nil || updatedPrefix == nil {
		return fmt.Errorf("failed to update prefix %s: %w", request.Prefix, err)
	}
	log.Info("prefix updated", "prefix", request.Prefix)
	return nil
}

// deleteObsoletePrefixes removes prefixes that are not defined in YAML
func (s *PrefixSync) deleteObsoletePrefixes(ctx context.Context, prefixes models.Prefixes) {
	desiredPrefixes := make(map[string]models.Prefix)
	for _, prefix := range prefixes.Prefix {
		desiredPrefixes[prefix.Prefix] = prefix
	}

	existingPrefixes := s.prefixSvc.ListAll(ctx)
	existingMap := make(map[string]nb.Prefix, len(existingPrefixes))
	for _, prefix := range existingPrefixes {
		existingMap[prefix.Prefix] = prefix
	}

	obsoletePrefixes := lo.OmitByKeys(existingMap, lo.Keys(desiredPrefixes))
	for _, prefix := range obsoletePrefixes {
		if prefix.Id != nil {
			_ = s.prefixSvc.Destroy(ctx, *prefix.Id)
		}
	}
}

func (s *PrefixSync) buildStatusReference(ctx context.Context, name string) (nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	status := s.statusSvc.GetByName(ctx, name)
	if status.Id == nil {
		return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{}, fmt.Errorf("status '%s' not found in Nautobot", name)
	}
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*status.Id), nil
}

func (s *PrefixSync) buildNamespaceReference(ctx context.Context, name string) (*nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	ns := s.namespaceSvc.GetByName(ctx, name)
	if ns.Id == nil {
		return nil, fmt.Errorf("namespace '%s' not found in Nautobot", name)
	}
	ref := helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*ns.Id)
	return &ref, nil
}

func (s *PrefixSync) buildRoleReference(ctx context.Context, name string) (nb.NullableApprovalWorkflowUser, error) {
	role := s.roleSvc.GetByName(ctx, name)
	if role.Id == nil {
		return nb.NullableApprovalWorkflowUser{}, fmt.Errorf("role '%s' not found in Nautobot", name)
	}
	return helpers.BuildNullableApprovalWorkflowUser(*role.Id), nil
}

func (s *PrefixSync) buildRirReference(ctx context.Context, name string) (nb.NullableBulkWritablePrefixRequestRir, error) {
	rir := s.rirSvc.GetByName(ctx, name)
	if rir.Id == nil {
		return nb.NullableBulkWritablePrefixRequestRir{}, fmt.Errorf("rir '%s' not found in Nautobot", name)
	}
	return helpers.BuildNullableBulkWritablePrefixRequestRir(*rir.Id), nil
}

func (s *PrefixSync) parseDateAllocated(dateStr string) (time.Time, error) {
	return time.Parse("2006-01-02 15:04:05", dateStr)
}

func (s *PrefixSync) buildLocationReference(ctx context.Context, name string) (nb.NullableBulkWritablePrefixRequestLocation, error) {
	location := s.locationSvc.GetByName(ctx, name)
	if location.Id == nil {
		return nb.NullableBulkWritablePrefixRequestLocation{}, fmt.Errorf("location '%s' not found in Nautobot", name)
	}
	return helpers.BuildNullableBulkWritablePrefixRequestLocation(*location.Id), nil
}

func (s *PrefixSync) buildVlanReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	vlan := s.vlanSvc.GetByName(ctx, name)
	if vlan.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*vlan.Id)
}

func (s *PrefixSync) buildTenantReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	tenant := s.tenantSvc.GetByName(ctx, name)
	if tenant.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*tenant.Id)
}

func (s *PrefixSync) buildTenantGroupID(ctx context.Context, name string) string {
	tg := s.tenantGroupSvc.GetByName(ctx, name)
	if tg.Id == nil {
		return ""
	}
	return *tg.Id
}

func (s *PrefixSync) buildVlanGroupID(ctx context.Context, name string) string {
	vg := s.vlanGroupSvc.GetByName(ctx, name)
	if vg.Id == nil {
		return ""
	}
	return *vg.Id
}

func (s *PrefixSync) buildVrfIDs(ctx context.Context, names []string) []string {
	var ids []string
	for _, name := range names {
		vrf := s.vrfSvc.GetByName(ctx, name)
		if vrf.Id != nil {
			ids = append(ids, *vrf.Id)
		}
	}
	return ids
}

func (s *PrefixSync) buildLocationIDs(ctx context.Context, names []string) []string {
	var ids []string
	for _, name := range names {
		location := s.locationSvc.GetByName(ctx, name)
		if location.Id != nil {
			ids = append(ids, *location.Id)
		}
	}
	return ids
}

func (s *PrefixSync) buildTagReferences(ctx context.Context, tagNames []string) []nb.ApprovalWorkflowStageResponseApprovalWorkflowStage {
	var tags []nb.ApprovalWorkflowStageResponseApprovalWorkflowStage
	for _, name := range tagNames {
		tag := s.tagSvc.GetByName(ctx, name)
		if tag.Id != nil {
			tags = append(tags, helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*tag.Id))
		}
	}
	return tags
}
