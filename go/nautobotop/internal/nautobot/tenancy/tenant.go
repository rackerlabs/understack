package tenancy

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

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
