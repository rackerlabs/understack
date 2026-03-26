package dcim

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type DeviceService struct {
	client *client.NautobotClient
}

func NewDeviceService(nautobotClient *client.NautobotClient) *DeviceService {
	return &DeviceService{
		client: nautobotClient,
	}
}

func (s *DeviceService) GetByName(ctx context.Context, name string) nb.Device {
	if device, ok := cache.FindByName(s.client.Cache, "devices", name, func(d nb.Device) string {
		return d.GetName()
	}); ok {
		return device
	}

	list, resp, err := s.client.APIClient.DcimAPI.DcimDevicesList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetDeviceByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Device{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Device{}
	}
	if list.Results[0].Id == nil {
		return nb.Device{}
	}

	return list.Results[0]
}

// ListByCluster returns all devices currently assigned to a cluster
func (s *DeviceService) ListByCluster(ctx context.Context, clusterID string) []nb.Device {
	list, resp, err := s.client.APIClient.DcimAPI.DcimDevicesList(ctx).Depth(2).Cluster([]string{clusterID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListDevicesByCluster", "failed to list", "cluster", clusterID, "error", err.Error(), "response_body", bodyString)
		return []nb.Device{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.Device{}
	}

	return list.Results
}

// AssignToCluster sets the cluster field on a device via partial update
func (s *DeviceService) AssignToCluster(ctx context.Context, deviceID string, clusterID *string) error {
	req := nb.PatchedWritableDeviceRequest{}
	if clusterID != nil {
		req.AdditionalProperties = map[string]interface{}{
			"cluster": map[string]interface{}{"id": *clusterID},
		}
	} else {
		req.AdditionalProperties = map[string]interface{}{
			"cluster": nil,
		}
	}

	_, resp, err := s.client.APIClient.DcimAPI.DcimDevicesPartialUpdate(ctx, deviceID).PatchedWritableDeviceRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("AssignDeviceToCluster", "failed to assign device to cluster", "device", deviceID, "error", err.Error(), "response_body", bodyString)
		return err
	}

	return nil
}
