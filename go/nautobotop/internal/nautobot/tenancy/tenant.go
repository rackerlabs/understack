package tenancy

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type TenantService struct {
	client *client.NautobotClient
}

func NewTenantService(nautobotClient *client.NautobotClient) *TenantService {
	return &TenantService{
		client: nautobotClient,
	}
}

func (s *TenantService) Create(ctx context.Context, req nb.TenantRequest) (*nb.Tenant, error) {
	tenant, resp, err := s.client.APIClient.TenancyAPI.TenancyTenantsCreate(ctx).TenantRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewTenant", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateTenant", "created tenant", tenant.Name)
	cache.AddToCollection(s.client.Cache, "tenants", *tenant)
	return tenant, nil
}

func (s *TenantService) GetByName(ctx context.Context, name string) nb.Tenant {
	if tenant, ok := cache.FindByName(s.client.Cache, "tenants", name, func(t nb.Tenant) string {
		return t.Name
	}); ok {
		return tenant
	}

	list, resp, err := s.client.APIClient.TenancyAPI.TenancyTenantsList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetTenantByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Tenant{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Tenant{}
	}
	if list.Results[0].Id == nil {
		return nb.Tenant{}
	}

	return list.Results[0]
}

func (s *TenantService) ListAll(ctx context.Context) []nb.Tenant {
	ids := s.client.GetChangeObjectIDS(ctx, "tenancy.tenant")
	list, resp, err := s.client.APIClient.TenancyAPI.TenancyTenantsList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllTenants", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.Tenant{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.Tenant{}
	}
	if list.Results[0].Id == nil {
		return []nb.Tenant{}
	}
	return list.Results
}

func (s *TenantService) Update(ctx context.Context, id string, req nb.TenantRequest) (*nb.Tenant, error) {
	tenant, resp, err := s.client.APIClient.TenancyAPI.TenancyTenantsUpdate(ctx, id).TenantRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateTenant", "failed to update", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated tenant", "id", id, "model", tenant.GetName())
	cache.UpdateInCollection(s.client.Cache, "tenants", *tenant, func(t nb.Tenant) bool {
		return t.Id != nil && *t.Id == id
	})
	return tenant, nil
}

func (s *TenantService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.TenancyAPI.TenancyTenantsDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyTenant", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "tenants", func(t nb.Tenant) bool {
		return t.Id != nil && *t.Id == id
	})
	return nil
}
