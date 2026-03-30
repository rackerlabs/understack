package ipam

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type VlanService struct {
	client *client.NautobotClient
}

func NewVlanService(nautobotClient *client.NautobotClient) *VlanService {
	return &VlanService{
		client: nautobotClient,
	}
}

func (s *VlanService) Create(ctx context.Context, req nb.VLANRequest) (*nb.VLAN, error) {
	vlan, resp, err := s.client.APIClient.IpamAPI.IpamVlansCreate(ctx).VLANRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewVlan", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateVlan", "created vlan", vlan.Name)
	cache.AddToCollection(s.client.Cache, "vlans", *vlan)

	return vlan, nil
}

func (s *VlanService) GetByName(ctx context.Context, name string) nb.VLAN {
	if vlan, ok := cache.FindByName(s.client.Cache, "vlans", name, func(v nb.VLAN) string {
		return v.Name
	}); ok {
		return vlan
	}

	list, resp, err := s.client.APIClient.IpamAPI.IpamVlansList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetVlanByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.VLAN{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.VLAN{}
	}
	if list.Results[0].Id == nil {
		return nb.VLAN{}
	}

	return list.Results[0]
}

func (s *VlanService) ListAll(ctx context.Context) []nb.VLAN {
	ids := s.client.GetChangeObjectIDS(ctx, "ipam.vlan")
	list, resp, err := s.client.APIClient.IpamAPI.IpamVlansList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllVlans", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.VLAN{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.VLAN{}
	}
	if list.Results[0].Id == nil {
		return []nb.VLAN{}
	}

	return list.Results
}

func (s *VlanService) Update(ctx context.Context, id string, req nb.VLANRequest) (*nb.VLAN, error) {
	vlan, resp, err := s.client.APIClient.IpamAPI.IpamVlansUpdate(ctx, id).VLANRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateVlan", "failed to update", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated vlan", "id", id, "model", vlan.GetName())

	cache.UpdateInCollection(s.client.Cache, "vlans", *vlan, func(v nb.VLAN) bool {
		return v.Id != nil && *v.Id == id
	})

	return vlan, nil
}

func (s *VlanService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.IpamAPI.IpamVlansDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyVlan", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "vlans", func(v nb.VLAN) bool {
		return v.Id != nil && *v.Id == id
	})

	return nil
}
