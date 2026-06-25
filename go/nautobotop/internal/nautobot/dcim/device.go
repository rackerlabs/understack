package dcim

import (
	"context"
	"net/http"

	"github.com/charmbracelet/log"
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

func (s *DeviceService) Create(ctx context.Context, req nb.WritableDeviceRequest) (*nb.Device, error) {
	device, resp, err := s.client.APIClient.DcimAPI.DcimDevicesCreate(ctx).WritableDeviceRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("CreateDevice", "failed to create", "name", req.GetName(), "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateDevice", "created device", device.GetName())
	cache.AddToCollection(s.client.Cache, "devices", *device)
	return device, nil
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

func (s *DeviceService) GetByID(ctx context.Context, id string) nb.Device {
	if id == "" {
		return nb.Device{}
	}
	if device, ok := cache.FindByID(s.client.Cache, "devices", id, func(d nb.Device) *string {
		return d.Id
	}); ok {
		return device
	}

	list, resp, err := s.client.APIClient.DcimAPI.DcimDevicesList(ctx).Depth(2).Id([]string{id}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetDeviceByID", "failed to get", "id", id, "error", err.Error(), "response_body", bodyString)
		return nb.Device{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == nil {
		return nb.Device{}
	}

	return list.Results[0]
}

func (s *DeviceService) ListAll(ctx context.Context) []nb.Device {
	return helpers.PaginatedList(
		ctx,
		func(ctx context.Context, limit, offset int32) ([]nb.Device, int32, *http.Response, error) {
			list, resp, err := s.client.APIClient.DcimAPI.DcimDevicesList(ctx).
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
		"ListAllDevices",
	)
}

func (s *DeviceService) Update(ctx context.Context, id string, req nb.WritableDeviceRequest) (*nb.Device, error) {
	device, resp, err := s.client.APIClient.DcimAPI.DcimDevicesUpdate(ctx, id).WritableDeviceRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateDevice", "failed to update", "id", id, "name", req.GetName(), "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated device", "id", id, "name", device.GetName())
	cache.UpdateInCollection(s.client.Cache, "devices", *device, func(d nb.Device) bool {
		return d.Id != nil && *d.Id == id
	})
	return device, nil
}

func (s *DeviceService) Destroy(ctx context.Context, id string) error {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("DestroyDevice", "failed to check ownership", "id", id, "error", err.Error())
		return err
	}
	if !owned {
		log.Warn("skipping destroy, object not created by user", "id", id, "user", s.client.Username)
		return nil
	}

	resp, err := s.client.APIClient.DcimAPI.DcimDevicesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyDevice", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "devices", func(d nb.Device) bool {
		return d.Id != nil && *d.Id == id
	})
	return nil
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
