package nautobot

import (
	"context"
	"fmt"
	"log"

	nb "github.com/nautobot/go-nautobot/v2"
)

type RackGroup struct {
	Name        string `yaml:"name"`
	Description string `yaml:"description"`
	Location    string `yaml:"location"`
}

func (n *NautobotClient) SyncRackGroup(ctx context.Context, rootLocations []RackGroup) error {
	for _, location := range rootLocations {
		_, err := n.syncOrUpdateRackGroup(ctx, &location, nil)
		if err != nil {
			return err
		}
	}
	return nil
}

func (n *NautobotClient) CreateRackGroup(ctx context.Context, req nb.RackGroupRequest) (*nb.RackGroup, error) {
	rackGroup, resp, err := n.Client.DcimAPI.DcimRackGroupsCreate(ctx).RackGroupRequest(req).Execute()
	if err != nil {
		logResponseBody(resp)
		return nil, fmt.Errorf("api error rack group %s: %w", req.Name, err)
	}
	log.Printf("created rack group: %s (ID: %s)", rackGroup.Name, rackGroup.Id)
	return rackGroup, nil
}

func (n *NautobotClient) UpdateRackGroup(ctx context.Context, id string, req nb.PatchedRackGroupRequest) (*nb.RackGroup, error) {
	loc, resp, err := n.Client.DcimAPI.DcimRackGroupsPartialUpdate(ctx, id).PatchedRackGroupRequest(req).Execute()
	if err != nil {
		logResponseBody(resp)
		return nil, err
	}
	log.Printf("updated rackgroup: id %s: Name:%s (%s)", id, loc.Name, loc.Display)
	return loc, nil
}

func (n *NautobotClient) FindRackGroupByName(ctx context.Context, name string) nb.RackGroup {
	list, _, err := n.Client.DcimAPI.DcimRackGroupsList(ctx).Limit(1000).Depth(0).Name([]string{name}).Execute()
	if err != nil {
		log.Printf("error fetching rack group by name '%s': %v", name, err)
		return nb.RackGroup{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return nb.RackGroup{}
	}
	return list.Results[0]
}

func (n *NautobotClient) syncOrUpdateRackGroup(ctx context.Context, input *RackGroup, parent *nb.RackGroup) (*nb.RackGroup, error) {
	existingRackGroupId := n.FindRackGroupByName(ctx, input.Name).Id
	existingLocationId := n.FindLocationByName(ctx, input.Location).Id

	if existingRackGroupId == "" {
		createRequest := newCreateRackGroupRequest(input, parent, existingLocationId)
		newLocation, err := n.CreateRackGroup(ctx, createRequest)
		if err != nil {
			return nil, fmt.Errorf("create failed for rack group %s: %w", input.Name, err)
		}
		return newLocation, nil
	}

	updateRequest := newUpdateRackGroupRequest(input, parent, existingLocationId)
	updatedLocation, err := n.UpdateRackGroup(ctx, existingRackGroupId, updateRequest)
	if err != nil {
		return nil, fmt.Errorf("update failed for rack group %s: %w", updatedLocation.Name, err)
	}

	return updatedLocation, nil
}

func newCreateRackGroupRequest(loc *RackGroup, parent *nb.RackGroup, location string) nb.RackGroupRequest {
	payload := nb.RackGroupRequest{
		Name:        loc.Name,
		Description: &loc.Description,
		Location:    *buildBulkWritableCableRequestStatus(location),
	}
	if parent != nil {
		payload.Parent = buildNullableBulkWritableCircuitRequestTenant(parent.Id)
	}
	return payload
}

func newUpdateRackGroupRequest(loc *RackGroup, parent *nb.RackGroup, location string) nb.PatchedRackGroupRequest {
	payload := nb.PatchedRackGroupRequest{
		Description: &loc.Description,
		Location:    buildBulkWritableCableRequestStatus(location),
	}
	if parent != nil {
		payload.Parent = buildNullableBulkWritableCircuitRequestTenant(parent.Id)
	}
	return payload
}
