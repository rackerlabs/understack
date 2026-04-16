package ipam

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type RirService struct {
	client *client.NautobotClient
}

func NewRirService(nautobotClient *client.NautobotClient) *RirService {
	return &RirService{
		client: nautobotClient,
	}
}

func (s *RirService) Create(ctx context.Context, req nb.RIRRequest) (*nb.RIR, error) {
	rir, resp, err := s.client.APIClient.IpamAPI.IpamRirsCreate(ctx).RIRRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewRir", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateRir", "created rir", rir.Name)
	cache.AddToCollection(s.client.Cache, "rirs", *rir)
	return rir, nil
}

func (s *RirService) GetByName(ctx context.Context, name string) nb.RIR {
	if rir, ok := cache.FindByName(s.client.Cache, "rirs", name, func(r nb.RIR) string {
		return r.Name
	}); ok {
		return rir
	}

	list, resp, err := s.client.APIClient.IpamAPI.IpamRirsList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetRirByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.RIR{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.RIR{}
	}
	if list.Results[0].Id == nil {
		return nb.RIR{}
	}

	return list.Results[0]
}

func (s *RirService) ListAll(ctx context.Context) []nb.RIR {
	ids := s.client.GetChangeObjectIDS(ctx, "ipam.rir")
	list, resp, err := s.client.APIClient.IpamAPI.IpamRirsList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllRirs", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.RIR{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.RIR{}
	}
	if list.Results[0].Id == nil {
		return []nb.RIR{}
	}
	return list.Results
}

func (s *RirService) Update(ctx context.Context, id string, req nb.RIRRequest) (*nb.RIR, error) {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("UpdateRir", "failed to check ownership", "id", id, "error", err.Error())
		return nil, err
	}
	if !owned {
		log.Warn("skipping update, object not created by user", "id", id, "user", s.client.Username)
		return nil, nil
	}

	rir, resp, err := s.client.APIClient.IpamAPI.IpamRirsUpdate(ctx, id).RIRRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateRir", "failed to update", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated rir", "id", id, "model", rir.GetName())
	cache.UpdateInCollection(s.client.Cache, "rirs", *rir, func(r nb.RIR) bool {
		return r.Id != nil && *r.Id == id
	})
	return rir, nil
}

func (s *RirService) Destroy(ctx context.Context, id string) error {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("DestroyRir", "failed to check ownership", "id", id, "error", err.Error())
		return err
	}
	if !owned {
		log.Warn("skipping destroy, object not created by user", "id", id, "user", s.client.Username)
		return nil
	}

	resp, err := s.client.APIClient.IpamAPI.IpamRirsDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyRir", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "rirs", func(r nb.RIR) bool {
		return r.Id != nil && *r.Id == id
	})
	return nil
}
