package dcim

import (
	"context"
	"net/http"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type LocationService struct {
	client *client.NautobotClient
}

func NewLocationService(nautobotClient *client.NautobotClient) *LocationService {
	return &LocationService{
		client: nautobotClient,
	}
}

func (s *LocationService) Create(ctx context.Context, req nb.LocationRequest) (*nb.Location, error) {
	location, resp, err := s.client.APIClient.DcimAPI.DcimLocationsCreate(ctx).LocationRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewLocation", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateLocation", "created location", location.Name)

	cache.AddToCollection(s.client.Cache, "locations", *location)

	return location, nil
}

func (s *LocationService) GetByName(ctx context.Context, name string) nb.Location {
	if location, ok := cache.FindByName(s.client.Cache, "locations", name, func(l nb.Location) string {
		return l.Name
	}); ok {
		return location
	}

	list, resp, err := s.client.APIClient.DcimAPI.DcimLocationsList(ctx).Depth(10).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetLocationByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Location{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Location{}
	}
	if list.Results[0].Id == nil {
		return nb.Location{}
	}

	return list.Results[0]
}

func (s *LocationService) GetByID(ctx context.Context, id string) nb.Location {
	if id == "" {
		return nb.Location{}
	}
	if location, ok := cache.FindByID(s.client.Cache, "locations", id, func(l nb.Location) *string {
		return l.Id
	}); ok {
		return location
	}

	list, resp, err := s.client.APIClient.DcimAPI.DcimLocationsList(ctx).Depth(10).Id([]string{id}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetLocationByID", "failed to get", "id", id, "error", err.Error(), "response_body", bodyString)
		return nb.Location{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == nil {
		return nb.Location{}
	}

	return list.Results[0]
}

func (s *LocationService) ListAll(ctx context.Context) []nb.Location {
	return helpers.PaginatedList(
		ctx,
		func(ctx context.Context, limit, offset int32) ([]nb.Location, int32, *http.Response, error) {
			list, resp, err := s.client.APIClient.DcimAPI.DcimLocationsList(ctx).
				Limit(limit).
				Offset(offset).
				Depth(10).
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
		"ListAllLocations",
	)
}

func (s *LocationService) Update(ctx context.Context, id string, req nb.LocationRequest) (*nb.Location, error) {
	location, resp, err := s.client.APIClient.DcimAPI.DcimLocationsUpdate(ctx, id).LocationRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateLocation", "failed to update UpdateLocation", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated location", "id", id, "model", location.GetName())
	cache.UpdateInCollection(s.client.Cache, "locations", *location, func(l nb.Location) bool {
		return l.Id != nil && *l.Id == id
	})

	return location, nil
}

func (s *LocationService) Destroy(ctx context.Context, id string) error {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("DestroyLocation", "failed to check ownership", "id", id, "error", err.Error())
		return err
	}
	if !owned {
		log.Warn("skipping destroy, object not created by user", "id", id, "user", s.client.Username)
		return nil
	}

	resp, err := s.client.APIClient.DcimAPI.DcimLocationsDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyLocation", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "locations", func(l nb.Location) bool {
		return l.Id != nil && *l.Id == id
	})

	return nil
}
