package tenancy

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type TenantGroupService struct {
	client *client.NautobotClient
}

func NewTenantGroupService(nautobotClient *client.NautobotClient) *TenantGroupService {
	return &TenantGroupService{
		client: nautobotClient,
	}
}

func (s *TenantGroupService) GetByName(ctx context.Context, name string) nb.TenantGroup {
	if tg, ok := cache.FindByName(s.client.Cache, "tenantgroups", name, func(t nb.TenantGroup) string {
		return t.Name
	}); ok {
		return tg
	}

	list, resp, err := s.client.APIClient.TenancyAPI.TenancyTenantGroupsList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetTenantGroupByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.TenantGroup{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.TenantGroup{}
	}
	if list.Results[0].Id == nil {
		return nb.TenantGroup{}
	}

	return list.Results[0]
}
