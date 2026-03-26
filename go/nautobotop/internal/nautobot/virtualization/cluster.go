package virtualization

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type ClusterService struct {
	client *client.NautobotClient
}

func NewClusterService(nautobotClient *client.NautobotClient) *ClusterService {
	return &ClusterService{
		client: nautobotClient,
	}
}

func (s *ClusterService) Create(ctx context.Context, req nb.ClusterRequest) (*nb.Cluster, error) {
	cluster, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClustersCreate(ctx).ClusterRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewCluster", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateCluster", "created cluster", cluster.Name)
	cache.AddToCollection(s.client.Cache, "clusters", *cluster)

	return cluster, nil
}

func (s *ClusterService) GetByName(ctx context.Context, name string) nb.Cluster {
	if cluster, ok := cache.FindByName(s.client.Cache, "clusters", name, func(c nb.Cluster) string {
		return c.Name
	}); ok {
		return cluster
	}

	list, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClustersList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetClusterByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Cluster{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Cluster{}
	}
	if list.Results[0].Id == nil {
		return nb.Cluster{}
	}

	return list.Results[0]
}

func (s *ClusterService) ListAll(ctx context.Context) []nb.Cluster {
	ids := s.client.GetChangeObjectIDS(ctx, "virtualization.cluster")
	list, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClustersList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllClusters", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.Cluster{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.Cluster{}
	}
	if list.Results[0].Id == nil {
		return []nb.Cluster{}
	}

	return list.Results
}

func (s *ClusterService) Update(ctx context.Context, id string, req nb.ClusterRequest) (*nb.Cluster, error) {
	cluster, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClustersUpdate(ctx, id).ClusterRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateCluster", "failed to update UpdateCluster", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated cluster", "id", id, "model", cluster.GetName())

	cache.UpdateInCollection(s.client.Cache, "clusters", *cluster, func(c nb.Cluster) bool {
		return c.Id != nil && *c.Id == id
	})

	return cluster, nil
}

func (s *ClusterService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClustersDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyCluster", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "clusters", func(c nb.Cluster) bool {
		return c.Id != nil && *c.Id == id
	})

	return nil
}
