package ipam

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type VrfService struct {
	client *client.NautobotClient
}

func NewVrfService(nautobotClient *client.NautobotClient) *VrfService {
	return &VrfService{
		client: nautobotClient,
	}
}

func (s *VrfService) GetByName(ctx context.Context, name string) nb.VRF {
	if vrf, ok := cache.FindByName(s.client.Cache, "vrfs", name, func(v nb.VRF) string {
		return v.Name
	}); ok {
		return vrf
	}

	list, resp, err := s.client.APIClient.IpamAPI.IpamVrfsList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetVrfByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.VRF{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.VRF{}
	}
	if list.Results[0].Id == nil {
		return nb.VRF{}
	}

	return list.Results[0]
}
