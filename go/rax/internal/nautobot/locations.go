package nautobot

import (
	"context"
	"fmt"
	"io"
	"log"
	"net/http"

	nb "github.com/nautobot/go-nautobot/v2"
)

type Location struct {
	ID           string     `yaml:"id,omitempty"`
	Name         string     `yaml:"name"`
	Description  string     `yaml:"description"`
	LocationType string     `yaml:"location_type"`
	Status       string     `yaml:"status"`
	Children     []Location `yaml:"children,omitempty"`
	Display      string     `yaml:"-"`
}

func (n *NautobotClient) SyncAllLocations(ctx context.Context, rootLocations []Location) error {
	for _, location := range rootLocations {
		if err := n.syncChildLocationsRecursive(ctx, &location, nil); err != nil {
			return fmt.Errorf("failed to sync root location %s: %w", location.Name, err)
		}
	}

	return n.DeleteOrphanedLocations(ctx, rootLocations)
}

func (n *NautobotClient) CreateNewLocation(ctx context.Context, req nb.LocationRequest) (*nb.Location, error) {
	loc, resp, err := n.Client.DcimAPI.DcimLocationsCreate(ctx).LocationRequest(req).Execute()
	if err != nil {
		logResponseBody(resp)
		return nil, err
	}
	log.Printf("Created location: %s", loc.Display)
	return loc, nil
}

func (n *NautobotClient) UpdateLocation(ctx context.Context, id string, req nb.PatchedLocationRequest) (*nb.Location, error) {
	loc, resp, err := n.Client.DcimAPI.DcimLocationsPartialUpdate(ctx, id).PatchedLocationRequest(req).Execute()
	if err != nil {
		logResponseBody(resp)
		return nil, err
	}
	log.Printf("Updated location: id %s: Name:%s (%s)", id, loc.Name, loc.Display)
	return loc, nil
}

func (n *NautobotClient) FindLocationByName(ctx context.Context, name string) nb.Location {
	list, _, err := n.Client.DcimAPI.DcimLocationsList(ctx).Depth(10).Name([]string{name}).Execute()
	if err != nil {
		log.Printf("Error fetching location type ID for name '%s': %v", name, err)
		return nb.Location{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return nb.Location{}
	}
	return list.Results[0]
}

func (n *NautobotClient) FindLocationByNameAndDisplayName(ctx context.Context, name, display string) nb.Location {
	list, _, err := n.Client.DcimAPI.DcimLocationsList(ctx).Depth(10).Execute()
	if err != nil {
		return nb.Location{}
	}

	for _, v := range list.Results {
		if v.Name == name && v.Display == display {
			return v
		}
	}

	return nb.Location{}
}

func (n *NautobotClient) GetAllNautobotLocations(ctx context.Context) ([]nb.Location, error) {
	offset := int32(0)
	limit := int32(1000)

	resp, _, err := n.Client.DcimAPI.DcimLocationsList(ctx).
		Limit(limit).
		Offset(offset).
		Execute()

	if err != nil {
		return nil, err
	}
	return resp.Results, nil
}

func (n *NautobotClient) DeleteOrphanedLocations(ctx context.Context, yamlRootLocations []Location) error {
	displayPaths := make(map[string]struct{})
	for _, root := range yamlRootLocations {
		collectDisplayPaths(&root, displayPaths)
	}

	existingLocations, err := n.GetAllNautobotLocations(ctx)
	if err != nil {
		return fmt.Errorf("failed to fetch Nautobot locations: %w", err)
	}

	for _, location := range existingLocations {
		if _, exists := displayPaths[location.Display]; !exists {
			log.Printf("Deleting orphaned location: %s", location.Name)
			if _, err := n.Client.DcimAPI.DcimLocationsDestroy(ctx, location.Id).Execute(); err != nil {
				log.Printf("Failed to delete location %s: %v", location.Name, err)
			}
		}
	}

	return nil
}

func (n *NautobotClient) syncChildLocationsRecursive(ctx context.Context, inputLocations *Location, parentLocation *nb.Location) error {
	location, err := n.syncOrUpdate(ctx, inputLocations, parentLocation)
	if err != nil {
		return err
	}
	for _, childLocation := range inputLocations.Children {
		if err := n.syncChildLocationsRecursive(ctx, &childLocation, location); err != nil {
			return err
		}
	}
	return nil
}

func newCreateLocationRequest(loc *Location, parent *nb.Location, statusID, typeID string) nb.LocationRequest {
	payload := nb.LocationRequest{
		Name:         loc.Name,
		Description:  &loc.Description,
		Status:       *buildBulkWritableCableRequestStatus(statusID),
		LocationType: *buildBulkWritableCableRequestStatus(typeID),
	}
	if parent != nil {
		payload.Parent = buildNullableBulkWritableCircuitRequestTenant(parent.Id)
	}
	return payload
}

func newUpdateLocationRequest(loc *Location, parent *nb.Location, statusID, typeID string) nb.PatchedLocationRequest {
	payload := nb.PatchedLocationRequest{
		Description:  &loc.Description,
		Status:       buildBulkWritableCableRequestStatus(statusID),
		LocationType: buildBulkWritableCableRequestStatus(typeID),
	}
	if parent != nil {
		payload.Parent = buildNullableBulkWritableCircuitRequestTenant(parent.Id)
	}
	return payload
}

func collectDisplayPaths(loc *Location, displayPathSet map[string]struct{}) {
	displayPathSet[loc.Display] = struct{}{}
	for i := range loc.Children {
		collectDisplayPaths(&loc.Children[i], displayPathSet)
	}
}

func (n *NautobotClient) syncOrUpdate(ctx context.Context, input *Location, parent *nb.Location) (*nb.Location, error) {
	existingLocation := n.FindLocationByNameAndDisplayName(ctx, input.Name, input.Display)
	status := n.FindStatus(ctx, input.Status)
	locationType := n.FindLocationType(ctx, input.LocationType)

	if existingLocation.Name == "" {
		createRequest := newCreateLocationRequest(input, parent, status.Id, locationType.Id)
		newLocation, err := n.CreateNewLocation(ctx, createRequest)
		if err != nil {
			return nil, fmt.Errorf("create failed for location %s: %w", input.Name, err)
		}
		return newLocation, nil
	}

	updateRequest := newUpdateLocationRequest(input, parent, status.Id, locationType.Id)
	updatedLocation, err := n.UpdateLocation(ctx, existingLocation.Id, updateRequest)
	if err != nil {
		return nil, fmt.Errorf("update failed for location %s: %w", existingLocation.Name, err)
	}

	return updatedLocation, nil
}

func logResponseBody(resp *http.Response) {
	if resp.Body == nil {
		return
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		log.Printf("failed to read response body")
		return
	}
	defer resp.Body.Close() //nolint:errcheck
	log.Printf("Create error: %s", string(body))
}
