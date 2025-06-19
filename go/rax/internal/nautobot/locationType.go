package nautobot

import (
	"context"
	"fmt"
	"log"
	"strings"

	nb "github.com/nautobot/go-nautobot/v2"
)

// LocationType defines the structure for a location type, including its children for hierarchical setup.
type LocationType struct {
	ID           string         `yaml:"id,omitempty"`
	Name         string         `yaml:"name"`
	Description  string         `yaml:"description"`
	Nestable     bool           `yaml:"nestable"`
	Status       string         `yaml:"status"` // Note: Status field is defined but not used in create/update logic below.
	ContentTypes []string       `yaml:"content_types"`
	Children     []LocationType `yaml:"children,omitempty"`
}

func (n *NautobotClient) SyncAllLocationTypes(ctx context.Context, rootLocations []LocationType) error {
	for _, locationType := range rootLocations {
		if err := n.syncChildLocationTypesRecursive(ctx, &locationType, nil); err != nil {
			return fmt.Errorf("failed to sync root location types %s: %w", locationType.Name, err)
		}
	}
	return nil
}

// CreateLocationType creates a new location type in Nautobot.
func (n *NautobotClient) CreateLocationType(ctx context.Context, req nb.LocationTypeRequest) (*nb.LocationType, error) {
	locationType, resp, err := n.Client.DcimAPI.DcimLocationTypesCreate(ctx).LocationTypeRequest(req).Execute()
	if err != nil {
		logResponseBody(resp)
		return nil, fmt.Errorf("API error creating location type %s: %w", req.Name, err)
	}
	log.Printf("Created location type: %s (ID: %s)", locationType.Name, locationType.Id)
	return locationType, nil
}

// UpdateLocationType updates an existing location type in Nautobot.
func (n *NautobotClient) UpdateLocationType(ctx context.Context, id string, req nb.PatchedLocationTypeRequest) (*nb.LocationType, error) {
	locationType, resp, err := n.Client.DcimAPI.DcimLocationTypesPartialUpdate(ctx, id).PatchedLocationTypeRequest(req).Execute()
	if err != nil {
		logResponseBody(resp)
		return nil, fmt.Errorf("API error updating location type ID %s: %w", id, err)
	}
	log.Printf("Updated location type: %s (ID: %s)", locationType.Name, id)
	return locationType, nil
}

// FindLocationType retrieves the ID of a location type by its name using an API call.
// Note: For bulk operations, consider using GetAllLocationTypesMap.
func (n *NautobotClient) FindLocationType(ctx context.Context, name string) nb.LocationType {
	list, _, err := n.Client.DcimAPI.DcimLocationTypesList(ctx).Name([]string{name}).Depth(0).Limit(1).Execute() // Filter by name
	if err != nil {
		log.Printf("Error fetching location type ID for name '%s': %v", name, err)
		return nb.LocationType{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return nb.LocationType{}
	}
	return list.Results[0]
}

func (n *NautobotClient) syncChildLocationTypesRecursive(ctx context.Context, inputLocations *LocationType, parentLocation *nb.LocationType) error {
	location, err := n.syncOrUpdateLocationTypes(ctx, inputLocations, parentLocation)
	if err != nil {
		return err
	}
	for _, childLocation := range inputLocations.Children {
		if err := n.syncChildLocationTypesRecursive(ctx, &childLocation, location); err != nil {
			return err
		}
	}
	return nil
}

func (n *NautobotClient) syncOrUpdateLocationTypes(ctx context.Context, input *LocationType, parent *nb.LocationType) (*nb.LocationType, error) {
	existing := n.FindLocationType(ctx, input.Name)
	if existing.Id == "" {
		req := n.newCreateLocationTypeRequest(ctx, input, parent)
		newLocType, err := n.CreateLocationType(ctx, req)
		if err != nil {
			return nil, fmt.Errorf("failed to create location type %q: %w", input.Name, err)
		}
		return newLocType, nil
	}

	req := n.newUpdateLocationTypeRequest(ctx, input, parent)
	updatedLocType, err := n.UpdateLocationType(ctx, existing.Id, req)
	if err != nil {
		return nil, fmt.Errorf("failed to update location type %q: %w", input.Name, err)
	}
	return updatedLocType, nil
}

func (n *NautobotClient) newCreateLocationTypeRequest(ctx context.Context, loc *LocationType, parent *nb.LocationType) nb.LocationTypeRequest {
	var contentTypesIds []string
	getAllContentType, _ := n.GetAllContentTypes(ctx)
	for _, v := range loc.ContentTypes {
		c := filterContentTypeID(getAllContentType, v)
		if c != nil {
			contentTypesIds = append(contentTypesIds, fmt.Sprintf("%s.%s", c.AppLabel, c.Model))
		}
	}

	payload := nb.LocationTypeRequest{
		Name:         loc.Name,
		Description:  &loc.Description,
		ContentTypes: contentTypesIds,
	}
	if parent != nil {
		payload.Parent = buildNullableBulkWritableCircuitRequestTenant(parent.Id)
	}
	return payload
}

func (n *NautobotClient) newUpdateLocationTypeRequest(ctx context.Context, loc *LocationType, parent *nb.LocationType) nb.PatchedLocationTypeRequest {
	var contentTypes []string
	getAllContentType, _ := n.GetAllContentTypes(ctx)
	for _, v := range loc.ContentTypes {
		c := filterContentTypeID(getAllContentType, v)
		if c != nil {
			contentTypes = append(contentTypes, fmt.Sprintf("%s.%s", c.AppLabel, c.Model))
		}
	}

	payload := nb.PatchedLocationTypeRequest{
		Description:  &loc.Description,
		Nestable:     &loc.Nestable,
		ContentTypes: contentTypes,
	}
	if parent != nil {
		payload.Parent = buildNullableBulkWritableCircuitRequestTenant(parent.Id)
	}
	return payload
}

// filterContentTypeID searches for a content type by various name formats within a list of content types.
func filterContentTypeID(list []nb.ContentType, name string) *nb.ContentType {
	for i, v := range list {
		// Check common ways a content type might be referenced.
		if strings.EqualFold(v.Display, name) || // e.g., "DCIM | Interface"
			strings.EqualFold(fmt.Sprintf("%s | %s", v.AppLabel, v.Model), name) || // e.g., "dcim | interface"
			strings.EqualFold(fmt.Sprintf("%s.%s", v.AppLabel, v.Model), name) { // e.g., "dcim.interface"
			return &list[i]
		}
	}
	return nil
}
