package nautobot

import (
	"context"
	"fmt"
	"log"

	nb "github.com/nautobot/go-nautobot/v2"
)

type Rack struct {
	Name        string `yaml:"name"`
	Description string `yaml:"description"`
	Location    string `yaml:"location"`
	Group       string `yaml:"group"`
	Role        string `yaml:"role"`
	Height      int    `yaml:"u_height"`
	FacilityID  string `yaml:"facility_id"`
	Status      string `yaml:"status"`
}

func (n *NautobotClient) SyncRack(ctx context.Context, racks []Rack) error {
	for _, rack := range racks {
		_, err := n.syncOrUpdateRack(ctx, &rack)
		if err != nil {
			log.Printf("failed to sync rack %s: %v", rack.Name, err)
		}
	}
	return nil
}

func (n *NautobotClient) syncOrUpdateRack(ctx context.Context, input *Rack) (*nb.Rack, error) {
	existing := n.FindRackByName(ctx, input.Name)
	location := n.FindLocationByName(ctx, input.Location)
	group := n.FindRackGroupByName(ctx, input.Group)
	status := n.FindStatus(ctx, input.Status)

	if existing.Id == "" {
		req := newCreateRackRequest(input, location.Id, group.Id, status.Id)
		return n.CreateRack(ctx, req)
	}

	req := newUpdateRackRequest(input, location.Id, group.Id, status.Id)
	return n.UpdateRack(ctx, existing.Id, req)
}

func (n *NautobotClient) CreateRack(ctx context.Context, req nb.WritableRackRequest) (*nb.Rack, error) {
	rack, resp, err := n.Client.DcimAPI.DcimRacksCreate(ctx).WritableRackRequest(req).Execute()
	if err != nil {
		logResponseBody(resp)
		return nil, fmt.Errorf("api error creating rack %s: %w", req.Name, err)
	}
	log.Printf("created rack: %s (ID: %s)", rack.Name, rack.Id)
	return rack, nil
}

func (n *NautobotClient) UpdateRack(ctx context.Context, id string, req nb.PatchedWritableRackRequest) (*nb.Rack, error) {
	rack, resp, err := n.Client.DcimAPI.DcimRacksPartialUpdate(ctx, id).PatchedWritableRackRequest(req).Execute()
	if err != nil {
		logResponseBody(resp)
		return nil, err
	}
	log.Printf("updated rack: id %s: Name:%s (%s)", id, rack.Name, rack.Display)
	return rack, nil
}

func (n *NautobotClient) FindRackByName(ctx context.Context, name string) nb.Rack {
	list, _, err := n.Client.DcimAPI.DcimRacksList(ctx).Limit(1000).Depth(0).Name([]string{name}).Execute()
	if err != nil || len(list.Results) == 0 {
		return nb.Rack{}
	}
	return list.Results[0]
}

// Helpers to build nullable/bulk objects for Nautobot API payloads

func newCreateRackRequest(r *Rack, locationID, groupID, statusID string) nb.WritableRackRequest {
	return nb.WritableRackRequest{
		Name:      r.Name,
		Location:  *buildBulkWritableCableRequestStatus(locationID),
		RackGroup: *buildNullableBulkWritableRackRequestRackGroup(groupID),
		Status:    *buildBulkWritableCableRequestStatus(statusID),
		UHeight:   nb.PtrInt32(int32(r.Height)),
	}
}

func newUpdateRackRequest(r *Rack, locationID, groupID, statusID string) nb.PatchedWritableRackRequest {
	return nb.PatchedWritableRackRequest{
		Location:  buildBulkWritableCableRequestStatus(locationID),
		RackGroup: *buildNullableBulkWritableRackRequestRackGroup(groupID),
		Status:    buildBulkWritableCableRequestStatus(statusID),
		UHeight:   nb.PtrInt32(int32(r.Height)),
	}
}
