package dcim

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type LocationTypeService struct {
	client *client.NautobotClient
}

func NewLocationTypeService(nautobotClient *client.NautobotClient) *LocationTypeService {
	return &LocationTypeService{
		client: nautobotClient,
	}
}

func (s *LocationTypeService) Create(ctx context.Context, req nb.LocationTypeRequest) (*nb.LocationType, error) {
	locationType, resp, err := s.client.APIClient.DcimAPI.DcimLocationTypesCreate(ctx).LocationTypeRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewLocationType", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateLocationType", "created device type", locationType.Name)
	cache.AddToCollection(s.client.Cache, "locationtypes", *locationType)

	return locationType, nil
}

func (s *LocationTypeService) GetByName(ctx context.Context, name string) nb.LocationType {
	if locationType, ok := cache.FindByName(s.client.Cache, "locationtypes", name, func(lt nb.LocationType) string {
		return lt.Name
	}); ok {
		return locationType
	}

	list, resp, err := s.client.APIClient.DcimAPI.DcimLocationTypesList(ctx).Depth(10).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetLocationTypeByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.LocationType{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.LocationType{}
	}
	if list.Results[0].Id == nil {
		return nb.LocationType{}
	}

	return list.Results[0]
}

func (s *LocationTypeService) ListAll(ctx context.Context) []nb.LocationType {
	ids := s.client.GetChangeObjectIDS(ctx, "dcim.locationtype")
	list, resp, err := s.client.APIClient.DcimAPI.DcimLocationTypesList(ctx).Id(ids).Depth(10).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllLocationTypes", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.LocationType{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.LocationType{}
	}
	if list.Results[0].Id == nil {
		return []nb.LocationType{}
	}

	return list.Results
}

func (s *LocationTypeService) Update(ctx context.Context, id string, req nb.LocationTypeRequest) (*nb.LocationType, error) {
	locationType, resp, err := s.client.APIClient.DcimAPI.DcimLocationTypesUpdate(ctx, id).LocationTypeRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateLocationType", "failed to update UpdateLocationType", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated device type", "id", id, "model", locationType.GetName())
	cache.UpdateInCollection(s.client.Cache, "locationtypes", *locationType, func(lt nb.LocationType) bool {
		return lt.Id != nil && *lt.Id == id
	})

	return locationType, nil
}

func (s *LocationTypeService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.DcimAPI.DcimLocationTypesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyLocationType", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}

	// Remove from cache
	cache.RemoveFromCollection(s.client.Cache, "locationtypes", func(lt nb.LocationType) bool {
		return lt.Id != nil && *lt.Id == id
	})

	return nil
}
