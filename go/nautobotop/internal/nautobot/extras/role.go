package extras

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
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

func (s *RoleService) Create(ctx context.Context, req nb.RoleRequest) (*nb.Role, error) {
	role, resp, err := s.client.APIClient.ExtrasAPI.ExtrasRolesCreate(ctx).RoleRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewRole", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateRole", "created role", role.Name)
	cache.AddToCollection(s.client.Cache, "roles", *role)
	return role, nil
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

func (s *RoleService) ListAll(ctx context.Context) []nb.Role {
	ids := s.client.GetChangeObjectIDS(ctx, "extras.role")
	list, resp, err := s.client.APIClient.ExtrasAPI.ExtrasRolesList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllRoles", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.Role{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.Role{}
	}
	if list.Results[0].Id == nil {
		return []nb.Role{}
	}
	return list.Results
}

func (s *RoleService) Update(ctx context.Context, id string, req nb.RoleRequest) (*nb.Role, error) {
	role, resp, err := s.client.APIClient.ExtrasAPI.ExtrasRolesUpdate(ctx, id).RoleRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateRole", "failed to update", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated role", "id", id, "model", role.GetName())
	cache.UpdateInCollection(s.client.Cache, "roles", *role, func(r nb.Role) bool {
		return r.Id != nil && *r.Id == id
	})
	return role, nil
}

func (s *RoleService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.ExtrasAPI.ExtrasRolesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyRole", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "roles", func(r nb.Role) bool {
		return r.Id != nil && *r.Id == id
	})
	return nil
}
