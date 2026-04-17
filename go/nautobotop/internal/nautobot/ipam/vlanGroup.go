package ipam

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type VlanGroupService struct {
	client *client.NautobotClient
}

func NewVlanGroupService(nautobotClient *client.NautobotClient) *VlanGroupService {
	return &VlanGroupService{
		client: nautobotClient,
	}
}

func (s *VlanGroupService) Create(ctx context.Context, req nb.VLANGroupRequest) (*nb.VLANGroup, error) {
	vlanGroup, resp, err := s.client.APIClient.IpamAPI.IpamVlanGroupsCreate(ctx).VLANGroupRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewVlanGroup", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateVlanGroup", "created vlan group", vlanGroup.Name)
	cache.AddToCollection(s.client.Cache, "vlangroups", *vlanGroup)

	return vlanGroup, nil
}

func (s *VlanGroupService) GetByName(ctx context.Context, name string) nb.VLANGroup {
	if vlanGroup, ok := cache.FindByName(s.client.Cache, "vlangroups", name, func(vg nb.VLANGroup) string {
		return vg.Name
	}); ok {
		return vlanGroup
	}

	list, resp, err := s.client.APIClient.IpamAPI.IpamVlanGroupsList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetVlanGroupByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.VLANGroup{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.VLANGroup{}
	}
	if list.Results[0].Id == nil {
		return nb.VLANGroup{}
	}

	return list.Results[0]
}

func (s *VlanGroupService) ListAll(ctx context.Context) []nb.VLANGroup {
	ids := s.client.GetChangeObjectIDS(ctx, "ipam.vlangroup")
	list, resp, err := s.client.APIClient.IpamAPI.IpamVlanGroupsList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllVlanGroups", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.VLANGroup{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.VLANGroup{}
	}
	if list.Results[0].Id == nil {
		return []nb.VLANGroup{}
	}

	return list.Results
}

func (s *VlanGroupService) Update(ctx context.Context, id string, req nb.VLANGroupRequest) (*nb.VLANGroup, error) {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("UpdateVlanGroup", "failed to check ownership", "id", id, "error", err.Error())
		return nil, err
	}
	if !owned {
		log.Warn("skipping update, object not created by user", "id", id, "user", s.client.Username)
		return nil, nil
	}

	vlanGroup, resp, err := s.client.APIClient.IpamAPI.IpamVlanGroupsUpdate(ctx, id).VLANGroupRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateVlanGroup", "failed to update UpdateVlanGroup", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated vlan group", "id", id, "model", vlanGroup.GetName())

	cache.UpdateInCollection(s.client.Cache, "vlangroups", *vlanGroup, func(vg nb.VLANGroup) bool {
		return vg.Id != nil && *vg.Id == id
	})

	return vlanGroup, nil
}

func (s *VlanGroupService) Destroy(ctx context.Context, id string) error {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("DestroyVlanGroup", "failed to check ownership", "id", id, "error", err.Error())
		return err
	}
	if !owned {
		log.Warn("skipping destroy, object not created by user", "id", id, "user", s.client.Username)
		return nil
	}

	resp, err := s.client.APIClient.IpamAPI.IpamVlanGroupsDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyVlanGroup", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "vlangroups", func(vg nb.VLANGroup) bool {
		return vg.Id != nil && *vg.Id == id
	})

	return nil
}
