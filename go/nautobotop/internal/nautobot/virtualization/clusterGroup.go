package virtualization

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type ClusterGroupService struct {
	client *client.NautobotClient
}

func NewClusterGroupService(nautobotClient *client.NautobotClient) *ClusterGroupService {
	return &ClusterGroupService{
		client: nautobotClient,
	}
}

func (s *ClusterGroupService) Create(ctx context.Context, req nb.ClusterGroupRequest) (*nb.ClusterGroup, error) {
	clusterGroup, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterGroupsCreate(ctx).ClusterGroupRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewClusterGroup", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateClusterGroup", "created cluster group", clusterGroup.Name)
	cache.AddToCollection(s.client.Cache, "clustergroups", *clusterGroup)

	return clusterGroup, nil
}

func (s *ClusterGroupService) GetByName(ctx context.Context, name string) nb.ClusterGroup {
	if clusterGroup, ok := cache.FindByName(s.client.Cache, "clustergroups", name, func(cg nb.ClusterGroup) string {
		return cg.Name
	}); ok {
		return clusterGroup
	}

	list, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterGroupsList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetClusterGroupByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.ClusterGroup{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.ClusterGroup{}
	}
	if list.Results[0].Id == nil {
		return nb.ClusterGroup{}
	}

	return list.Results[0]
}

func (s *ClusterGroupService) ListAll(ctx context.Context) []nb.ClusterGroup {
	ids := s.client.GetChangeObjectIDS(ctx, "virtualization.clustergroup")
	list, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterGroupsList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllClusterGroups", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.ClusterGroup{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.ClusterGroup{}
	}
	if list.Results[0].Id == nil {
		return []nb.ClusterGroup{}
	}

	return list.Results
}

func (s *ClusterGroupService) Update(ctx context.Context, id string, req nb.ClusterGroupRequest) (*nb.ClusterGroup, error) {
	clusterGroup, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterGroupsUpdate(ctx, id).ClusterGroupRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateClusterGroup", "failed to update UpdateClusterGroup", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated cluster group", "id", id, "model", clusterGroup.GetName())

	cache.UpdateInCollection(s.client.Cache, "clustergroups", *clusterGroup, func(cg nb.ClusterGroup) bool {
		return cg.Id != nil && *cg.Id == id
	})

	return clusterGroup, nil
}

func (s *ClusterGroupService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterGroupsDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyClusterGroup", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "clustergroups", func(cg nb.ClusterGroup) bool {
		return cg.Id != nil && *cg.Id == id
	})

	return nil
}
