package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/ipam"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/tenancy"
	"github.com/samber/lo"
	"go.yaml.in/yaml/v3"
)

type NamespaceSync struct {
	client         *client.NautobotClient
	namespaceSvc   *ipam.NamespaceService
	locationSvc    *dcim.LocationService
	tenantSvc      *tenancy.TenantService
	tenantGroupSvc *tenancy.TenantGroupService
}

func NewNamespaceSync(nautobotClient *client.NautobotClient) *NamespaceSync {
	return &NamespaceSync{
		client:         nautobotClient.GetClient(),
		namespaceSvc:   ipam.NewNamespaceService(nautobotClient),
		locationSvc:    dcim.NewLocationService(nautobotClient.GetClient()),
		tenantSvc:      tenancy.NewTenantService(nautobotClient),
		tenantGroupSvc: tenancy.NewTenantGroupService(nautobotClient),
	}
}

func (s *NamespaceSync) SyncAll(ctx context.Context, data map[string]string) error {
	var namespaces models.Namespaces
	for key, f := range data {
		var yml []models.Namespace
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		namespaces.Namespace = append(namespaces.Namespace, yml...)
	}

	for _, ns := range namespaces.Namespace {
		if err := s.syncSingleNamespace(ctx, ns); err != nil {
			return err
		}
	}
	s.deleteObsoleteNamespaces(ctx, namespaces)

	return nil
}

func (s *NamespaceSync) syncSingleNamespace(ctx context.Context, namespace models.Namespace) error {
	existingNamespace := s.namespaceSvc.GetByName(ctx, namespace.Name)

	nsRequest := nb.NamespaceRequest{
		Name:        namespace.Name,
		Description: nb.PtrString(namespace.Description),
	}

	if namespace.Location != "" {
		nsRequest.Location = s.buildLocationReference(ctx, namespace.Location)
	}

	if namespace.Tenant != "" {
		nsRequest.Tenant = s.buildTenantReference(ctx, namespace.Tenant)
	}

	customFields := make(map[string]interface{})
	if namespace.TenantGroup != "" {
		customFields["tenant_group"] = s.buildTenantGroupID(ctx, namespace.TenantGroup)
	}
	if len(customFields) > 0 {
		nsRequest.CustomFields = customFields
	}

	if existingNamespace.Id == nil {
		return s.createNamespace(ctx, nsRequest)
	}

	if !helpers.CompareJSONFields(existingNamespace, nsRequest) {
		return s.updateNamespace(ctx, *existingNamespace.Id, nsRequest)
	}

	log.Info("namespace unchanged, skipping update", "name", nsRequest.Name)
	return nil
}

func (s *NamespaceSync) createNamespace(ctx context.Context, request nb.NamespaceRequest) error {
	createdNamespace, err := s.namespaceSvc.Create(ctx, request)
	if err != nil || createdNamespace == nil {
		return fmt.Errorf("failed to create namespace %s: %w", request.Name, err)
	}
	log.Info("namespace created", "name", request.Name)
	return nil
}

func (s *NamespaceSync) updateNamespace(ctx context.Context, id string, request nb.NamespaceRequest) error {
	updatedNamespace, err := s.namespaceSvc.Update(ctx, id, request)
	if err != nil || updatedNamespace == nil {
		return fmt.Errorf("failed to update namespace %s: %w", request.Name, err)
	}
	log.Info("namespace updated", "name", request.Name)
	return nil
}

func (s *NamespaceSync) deleteObsoleteNamespaces(ctx context.Context, namespaces models.Namespaces) {
	desiredNamespaces := make(map[string]models.Namespace)
	for _, ns := range namespaces.Namespace {
		desiredNamespaces[ns.Name] = ns
	}

	existingNamespaces := s.namespaceSvc.ListAll(ctx)
	existingMap := make(map[string]nb.Namespace, len(existingNamespaces))
	for _, ns := range existingNamespaces {
		existingMap[ns.Name] = ns
	}

	obsoleteNamespaces := lo.OmitByKeys(existingMap, lo.Keys(desiredNamespaces))
	for _, ns := range obsoleteNamespaces {
		if ns.Id != nil {
			_ = s.namespaceSvc.Destroy(ctx, *ns.Id)
		}
	}
}

func (s *NamespaceSync) buildLocationReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	location := s.locationSvc.GetByName(ctx, name)
	if location.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*location.Id)
}

func (s *NamespaceSync) buildTenantReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	tenant := s.tenantSvc.GetByName(ctx, name)
	if tenant.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*tenant.Id)
}

func (s *NamespaceSync) buildTenantGroupID(ctx context.Context, name string) string {
	tg := s.tenantGroupSvc.GetByName(ctx, name)
	if tg.Id == nil {
		return ""
	}
	return *tg.Id
}
