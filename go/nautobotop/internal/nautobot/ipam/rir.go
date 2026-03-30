package ipam

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

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
