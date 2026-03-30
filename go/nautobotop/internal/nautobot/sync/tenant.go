package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/extras"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/tenancy"
	"github.com/samber/lo"
	"go.yaml.in/yaml/v3"
)

type TenantSync struct {
	client         *client.NautobotClient
	tenantSvc      *tenancy.TenantService
	tenantGroupSvc *tenancy.TenantGroupService
	tagSvc         *extras.TagService
}

func NewTenantSync(nautobotClient *client.NautobotClient) *TenantSync {
	return &TenantSync{
		client:         nautobotClient.GetClient(),
		tenantSvc:      tenancy.NewTenantService(nautobotClient),
		tenantGroupSvc: tenancy.NewTenantGroupService(nautobotClient),
		tagSvc:         extras.NewTagService(nautobotClient),
	}
}

func (s *TenantSync) SyncAll(ctx context.Context, data map[string]string) error {
	var tenants models.Tenants
	for key, f := range data {
		var yml []models.Tenant
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		tenants.Tenant = append(tenants.Tenant, yml...)
	}

	for _, t := range tenants.Tenant {
		if err := s.syncSingleTenant(ctx, t); err != nil {
			return err
		}
	}
	s.deleteObsoleteTenants(ctx, tenants)
	return nil
}

func (s *TenantSync) syncSingleTenant(ctx context.Context, tenant models.Tenant) error {
	existing := s.tenantSvc.GetByName(ctx, tenant.Name)

	tenantRequest := nb.TenantRequest{
		Name: tenant.Name,
	}
	if tenant.Description != "" {
		tenantRequest.Description = nb.PtrString(tenant.Description)
	}
	if tenant.Comments != "" {
		tenantRequest.Comments = nb.PtrString(tenant.Comments)
	}
	if tenant.TenantGroup != "" {
		tenantRequest.TenantGroup = s.buildTenantGroupReference(ctx, tenant.TenantGroup)
	}
	if len(tenant.Tags) > 0 {
		tenantRequest.Tags = s.buildTagReferences(ctx, tenant.Tags)
	}

	if existing.Id == nil {
		return s.createTenant(ctx, tenantRequest)
	}
	if !helpers.CompareJSONFields(existing, tenantRequest) {
		return s.updateTenant(ctx, *existing.Id, tenantRequest)
	}
	log.Info("tenant unchanged, skipping update", "name", tenantRequest.Name)
	return nil
}

func (s *TenantSync) createTenant(ctx context.Context, request nb.TenantRequest) error {
	created, err := s.tenantSvc.Create(ctx, request)
	if err != nil || created == nil {
		return fmt.Errorf("failed to create tenant %s: %w", request.Name, err)
	}
	log.Info("tenant created", "name", request.Name)
	return nil
}

func (s *TenantSync) updateTenant(ctx context.Context, id string, request nb.TenantRequest) error {
	updated, err := s.tenantSvc.Update(ctx, id, request)
	if err != nil || updated == nil {
		return fmt.Errorf("failed to update tenant %s: %w", request.Name, err)
	}
	log.Info("tenant updated", "name", request.Name)
	return nil
}

func (s *TenantSync) deleteObsoleteTenants(ctx context.Context, tenants models.Tenants) {
	desired := make(map[string]models.Tenant)
	for _, t := range tenants.Tenant {
		desired[t.Name] = t
	}

	existing := s.tenantSvc.ListAll(ctx)
	existingMap := make(map[string]nb.Tenant, len(existing))
	for _, t := range existing {
		existingMap[t.Name] = t
	}

	obsolete := lo.OmitByKeys(existingMap, lo.Keys(desired))
	for _, t := range obsolete {
		if t.Id != nil {
			_ = s.tenantSvc.Destroy(ctx, *t.Id)
		}
	}
}

func (s *TenantSync) buildTenantGroupReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	tg := s.tenantGroupSvc.GetByName(ctx, name)
	if tg.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*tg.Id)
}

func (s *TenantSync) buildTagReferences(ctx context.Context, tagNames []string) []nb.ApprovalWorkflowStageResponseApprovalWorkflowStage {
	var tags []nb.ApprovalWorkflowStageResponseApprovalWorkflowStage
	for _, name := range tagNames {
		tag := s.tagSvc.GetByName(ctx, name)
		if tag.Id != nil {
			tags = append(tags, helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*tag.Id))
		}
	}
	return tags
}
