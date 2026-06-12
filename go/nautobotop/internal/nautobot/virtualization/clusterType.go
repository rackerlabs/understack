package virtualization

import (
	"context"
	"net/http"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type ClusterTypeService struct {
	client *client.NautobotClient
}

func NewClusterTypeService(nautobotClient *client.NautobotClient) *ClusterTypeService {
	return &ClusterTypeService{
		client: nautobotClient,
	}
}

func (s *ClusterTypeService) Create(ctx context.Context, req nb.ClusterTypeRequest) (*nb.ClusterType, error) {
	clusterType, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterTypesCreate(ctx).ClusterTypeRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewClusterType", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateClusterType", "created cluster type", clusterType.Name)
	cache.AddToCollection(s.client.Cache, "clustertypes", *clusterType)

	return clusterType, nil
}

func (s *ClusterTypeService) GetByName(ctx context.Context, name string) nb.ClusterType {
	if clusterType, ok := cache.FindByName(s.client.Cache, "clustertypes", name, func(ct nb.ClusterType) string {
		return ct.Name
	}); ok {
		return clusterType
	}

	list, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterTypesList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetClusterTypeByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.ClusterType{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.ClusterType{}
	}
	if list.Results[0].Id == nil {
		return nb.ClusterType{}
	}

	return list.Results[0]
}

func (s *ClusterTypeService) GetByID(ctx context.Context, id string) nb.ClusterType {
	if id == "" {
		return nb.ClusterType{}
	}
	if clusterType, ok := cache.FindByID(s.client.Cache, "clustertypes", id, func(ct nb.ClusterType) *string {
		return ct.Id
	}); ok {
		return clusterType
	}

	list, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterTypesList(ctx).Depth(2).Id([]string{id}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetClusterTypeByID", "failed to get", "id", id, "error", err.Error(), "response_body", bodyString)
		return nb.ClusterType{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == nil {
		return nb.ClusterType{}
	}

	return list.Results[0]
}

func (s *ClusterTypeService) ListAll(ctx context.Context) []nb.ClusterType {
	return helpers.PaginatedList(
		ctx,
		func(ctx context.Context, limit, offset int32) ([]nb.ClusterType, int32, *http.Response, error) {
			list, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterTypesList(ctx).
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
		"ListAllClusterTypes",
	)
}

func (s *ClusterTypeService) Update(ctx context.Context, id string, req nb.ClusterTypeRequest) (*nb.ClusterType, error) {
	clusterType, resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterTypesUpdate(ctx, id).ClusterTypeRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateClusterType", "failed to update UpdateClusterType", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated cluster type", "id", id, "model", clusterType.GetName())

	cache.UpdateInCollection(s.client.Cache, "clustertypes", *clusterType, func(ct nb.ClusterType) bool {
		return ct.Id != nil && *ct.Id == id
	})

	return clusterType, nil
}

func (s *ClusterTypeService) Destroy(ctx context.Context, id string) error {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("DestroyClusterType", "failed to check ownership", "id", id, "error", err.Error())
		return err
	}
	if !owned {
		log.Warn("skipping destroy, object not created by user", "id", id, "user", s.client.Username)
		return nil
	}

	resp, err := s.client.APIClient.VirtualizationAPI.VirtualizationClusterTypesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyClusterType", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "clustertypes", func(ct nb.ClusterType) bool {
		return ct.Id != nil && *ct.Id == id
	})

	return nil
}
