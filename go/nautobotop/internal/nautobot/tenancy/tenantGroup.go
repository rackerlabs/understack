package tenancy

import (
	"context"
	"net/http"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
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

func (s *TenantGroupService) Create(ctx context.Context, req nb.TenantGroupRequest) (*nb.TenantGroup, error) {
	tg, resp, err := s.client.APIClient.TenancyAPI.TenancyTenantGroupsCreate(ctx).TenantGroupRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewTenantGroup", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateTenantGroup", "created tenant group", tg.Name)
	cache.AddToCollection(s.client.Cache, "tenantgroups", *tg)
	return tg, nil
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

func (s *TenantGroupService) GetByID(ctx context.Context, id string) nb.TenantGroup {
	if id == "" {
		return nb.TenantGroup{}
	}
	if tg, ok := cache.FindByID(s.client.Cache, "tenantgroups", id, func(t nb.TenantGroup) *string {
		return t.Id
	}); ok {
		return tg
	}

	list, resp, err := s.client.APIClient.TenancyAPI.TenancyTenantGroupsList(ctx).Depth(2).Id([]string{id}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetTenantGroupByID", "failed to get", "id", id, "error", err.Error(), "response_body", bodyString)
		return nb.TenantGroup{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == nil {
		return nb.TenantGroup{}
	}

	return list.Results[0]
}

func (s *TenantGroupService) ListAll(ctx context.Context) []nb.TenantGroup {
	return helpers.PaginatedList(
		ctx,
		func(ctx context.Context, limit, offset int32) ([]nb.TenantGroup, int32, *http.Response, error) {
			list, resp, err := s.client.APIClient.TenancyAPI.TenancyTenantGroupsList(ctx).
				Limit(limit).
				Offset(offset).
				Depth(2).
				Execute()
			if err != nil {
				return nil, 0, resp, err
			}
			if list == nil {
				return nil, 0, resp, nil
			}
			return list.Results, list.Count, resp, nil
		},
		s.client.AddReport,
		"ListAllTenantGroups",
	)
}

func (s *TenantGroupService) Update(ctx context.Context, id string, req nb.TenantGroupRequest) (*nb.TenantGroup, error) {
	tg, resp, err := s.client.APIClient.TenancyAPI.TenancyTenantGroupsUpdate(ctx, id).TenantGroupRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateTenantGroup", "failed to update", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated tenant group", "id", id, "model", tg.GetName())
	cache.UpdateInCollection(s.client.Cache, "tenantgroups", *tg, func(t nb.TenantGroup) bool {
		return t.Id != nil && *t.Id == id
	})
	return tg, nil
}

func (s *TenantGroupService) Destroy(ctx context.Context, id string) error {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("DestroyTenantGroup", "failed to check ownership", "id", id, "error", err.Error())
		return err
	}
	if !owned {
		log.Warn("skipping destroy, object not created by user", "id", id, "user", s.client.Username)
		return nil
	}

	resp, err := s.client.APIClient.TenancyAPI.TenancyTenantGroupsDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyTenantGroup", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "tenantgroups", func(t nb.TenantGroup) bool {
		return t.Id != nil && *t.Id == id
	})
	return nil
}
