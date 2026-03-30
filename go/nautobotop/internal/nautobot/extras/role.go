package extras

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type RoleService struct {
	client *client.NautobotClient
}

func NewRoleService(nautobotClient *client.NautobotClient) *RoleService {
	return &RoleService{
		client: nautobotClient,
	}
}

func (s *RoleService) GetByName(ctx context.Context, name string) nb.Role {
	if role, ok := cache.FindByName(s.client.Cache, "roles", name, func(r nb.Role) string {
		return r.Name
	}); ok {
		return role
	}

	list, resp, err := s.client.APIClient.ExtrasAPI.ExtrasRolesList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetRoleByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Role{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Role{}
	}
	if list.Results[0].Id == nil {
		return nb.Role{}
	}

	return list.Results[0]
}
