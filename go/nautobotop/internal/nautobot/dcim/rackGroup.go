package dcim

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type RackGroupService struct {
	client *client.NautobotClient
}

func NewRackGroupService(nautobotClient *client.NautobotClient) *RackGroupService {
	return &RackGroupService{
		client: nautobotClient,
	}
}

func (s *RackGroupService) Create(ctx context.Context, req nb.RackGroupRequest) (*nb.RackGroup, error) {
	rackGroup, resp, err := s.client.APIClient.DcimAPI.DcimRackGroupsCreate(ctx).RackGroupRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewRackGroup", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateRackGroup", "created rack group", rackGroup.Name)
	cache.AddToCollection(s.client.Cache, "rackgroups", *rackGroup)

	return rackGroup, nil
}

func (s *RackGroupService) GetByName(ctx context.Context, name string) nb.RackGroup {
	if rackGroup, ok := cache.FindByName(s.client.Cache, "rackgroups", name, func(rg nb.RackGroup) string {
		return rg.Name
	}); ok {
		return rackGroup
	}

	list, resp, err := s.client.APIClient.DcimAPI.DcimRackGroupsList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetRackGroupByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.RackGroup{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.RackGroup{}
	}
	if list.Results[0].Id == nil {
		return nb.RackGroup{}
	}

	return list.Results[0]
}

func (s *RackGroupService) ListAll(ctx context.Context) []nb.RackGroup {
	ids := s.client.GetChangeObjectIDS(ctx, "dcim.rackgroup")
	list, resp, err := s.client.APIClient.DcimAPI.DcimRackGroupsList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllRackGroups", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.RackGroup{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.RackGroup{}
	}
	if list.Results[0].Id == nil {
		return []nb.RackGroup{}
	}

	return list.Results
}

func (s *RackGroupService) Update(ctx context.Context, id string, req nb.RackGroupRequest) (*nb.RackGroup, error) {
	rackGroup, resp, err := s.client.APIClient.DcimAPI.DcimRackGroupsUpdate(ctx, id).RackGroupRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateRackGroup", "failed to update UpdateRackGroup", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated rack group", "id", id, "model", rackGroup.GetName())

	cache.UpdateInCollection(s.client.Cache, "rackgroups", *rackGroup, func(rg nb.RackGroup) bool {
		return rg.Id != nil && *rg.Id == id
	})

	return rackGroup, nil
}

func (s *RackGroupService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.DcimAPI.DcimRackGroupsDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyRackGroup", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "rackgroups", func(rg nb.RackGroup) bool {
		return rg.Id != nil && *rg.Id == id
	})

	return nil
}
