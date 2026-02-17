package dcim

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type RackService struct {
	client *client.NautobotClient
}

func NewRackService(nautobotClient *client.NautobotClient) *RackService {
	return &RackService{
		client: nautobotClient,
	}
}

func (s *RackService) Create(ctx context.Context, req nb.WritableRackRequest) (*nb.Rack, error) {
	rack, resp, err := s.client.APIClient.DcimAPI.DcimRacksCreate(ctx).WritableRackRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewRack", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateRack", "created rack", rack.Name)
	cache.AddToCollection(s.client.Cache, "racks", *rack)

	return rack, nil
}

func (s *RackService) GetByName(ctx context.Context, name string) nb.Rack {
	if rack, ok := cache.FindByName(s.client.Cache, "racks", name, func(r nb.Rack) string {
		return r.Name
	}); ok {
		return rack
	}
	list, resp, err := s.client.APIClient.DcimAPI.DcimRacksList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetRackByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Rack{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Rack{}
	}
	if list.Results[0].Id == nil {
		return nb.Rack{}
	}

	return list.Results[0]
}

func (s *RackService) ListAll(ctx context.Context) []nb.Rack {
	ids := s.client.GetChangeObjectIDS(ctx, "dcim.rack")
	list, resp, err := s.client.APIClient.DcimAPI.DcimRacksList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllRacks", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.Rack{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.Rack{}
	}
	if list.Results[0].Id == nil {
		return []nb.Rack{}
	}

	return list.Results
}

func (s *RackService) Update(ctx context.Context, id string, req nb.WritableRackRequest) (*nb.Rack, error) {
	rack, resp, err := s.client.APIClient.DcimAPI.DcimRacksUpdate(ctx, id).WritableRackRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateRack", "failed to update", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated rack", "id", id, "model", rack.Name)

	cache.UpdateInCollection(s.client.Cache, "racks", *rack, func(r nb.Rack) bool {
		return r.Id != nil && *r.Id == id
	})

	return rack, nil
}

func (s *RackService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.DcimAPI.DcimRacksDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyRack", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "racks", func(r nb.Rack) bool {
		return r.Id != nil && *r.Id == id
	})
	return nil
}
