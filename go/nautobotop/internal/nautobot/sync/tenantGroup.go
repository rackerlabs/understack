package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/tenancy"
	"github.com/samber/lo"
	"go.yaml.in/yaml/v3"
)

type TenantGroupSync struct {
	client         *client.NautobotClient
	tenantGroupSvc *tenancy.TenantGroupService
}

func NewTenantGroupSync(nautobotClient *client.NautobotClient) *TenantGroupSync {
	return &TenantGroupSync{
		client:         nautobotClient.GetClient(),
		tenantGroupSvc: tenancy.NewTenantGroupService(nautobotClient),
	}
}

func (s *TenantGroupSync) SyncAll(ctx context.Context, data map[string]string) error {
	var tenantGroups models.TenantGroups
	for key, f := range data {
		var yml []models.TenantGroup
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		tenantGroups.TenantGroup = append(tenantGroups.TenantGroup, yml...)
	}

	for _, tg := range tenantGroups.TenantGroup {
		if err := s.syncSingleTenantGroup(ctx, tg); err != nil {
			return err
		}
	}
	s.deleteObsoleteTenantGroups(ctx, tenantGroups)
	return nil
}

func (s *TenantGroupSync) syncSingleTenantGroup(ctx context.Context, tg models.TenantGroup) error {
	existing := s.tenantGroupSvc.GetByName(ctx, tg.Name)

	tgRequest := nb.TenantGroupRequest{
		Name: tg.Name,
	}
	if tg.Description != "" {
		tgRequest.Description = nb.PtrString(tg.Description)
	}
	if tg.Parent != "" {
		tgRequest.Parent = s.buildParentReference(ctx, tg.Parent)
	}

	if existing.Id == nil {
		return s.createTenantGroup(ctx, tgRequest)
	}
	if !helpers.CompareJSONFields(existing, tgRequest) {
		return s.updateTenantGroup(ctx, *existing.Id, tgRequest)
	}
	log.Info("tenant group unchanged, skipping update", "name", tgRequest.Name)
	return nil
}

func (s *TenantGroupSync) createTenantGroup(ctx context.Context, request nb.TenantGroupRequest) error {
	created, err := s.tenantGroupSvc.Create(ctx, request)
	if err != nil || created == nil {
		return fmt.Errorf("failed to create tenant group %s: %w", request.Name, err)
	}
	log.Info("tenant group created", "name", request.Name)
	return nil
}

func (s *TenantGroupSync) updateTenantGroup(ctx context.Context, id string, request nb.TenantGroupRequest) error {
	updated, err := s.tenantGroupSvc.Update(ctx, id, request)
	if err != nil || updated == nil {
		return fmt.Errorf("failed to update tenant group %s: %w", request.Name, err)
	}
	log.Info("tenant group updated", "name", request.Name)
	return nil
}

func (s *TenantGroupSync) deleteObsoleteTenantGroups(ctx context.Context, tenantGroups models.TenantGroups) {
	desired := make(map[string]models.TenantGroup)
	for _, tg := range tenantGroups.TenantGroup {
		desired[tg.Name] = tg
	}

	existing := s.tenantGroupSvc.ListAll(ctx)
	existingMap := make(map[string]nb.TenantGroup, len(existing))
	for _, tg := range existing {
		existingMap[tg.Name] = tg
	}

	obsolete := lo.OmitByKeys(existingMap, lo.Keys(desired))
	for _, tg := range obsolete {
		if tg.Id != nil {
			_ = s.tenantGroupSvc.Destroy(ctx, *tg.Id)
		}
	}
}

func (s *TenantGroupSync) buildParentReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	parent := s.tenantGroupSvc.GetByName(ctx, name)
	if parent.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*parent.Id)
}
