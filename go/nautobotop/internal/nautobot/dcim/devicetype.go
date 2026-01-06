package dcim

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type DeviceTypeService struct {
	client *client.NautobotClient
}

func NewDeviceTypeService(nautobotClient *client.NautobotClient) *DeviceTypeService {
	return &DeviceTypeService{
		client: nautobotClient,
	}
}

func (s *DeviceTypeService) Create(ctx context.Context, req nb.WritableDeviceTypeRequest) (*nb.DeviceType, error) {
	deviceType, resp, err := s.client.APIClient.DcimAPI.DcimDeviceTypesCreate(ctx).WritableDeviceTypeRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewDeviceType", "failed to create", "model", req.Model, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateDeviceType", "created device type", deviceType.Display)
	return deviceType, nil
}

func (s *DeviceTypeService) GetByName(ctx context.Context, name string) nb.DeviceType {
	list, resp, err := s.client.APIClient.DcimAPI.DcimDeviceTypesList(ctx).Depth(10).Model([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetDeviceTypeByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.DeviceType{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return nb.DeviceType{}
	}
	return list.Results[0]
}

func (s *DeviceTypeService) ListAll(ctx context.Context) []nb.DeviceType {
	ids := s.client.GetChangeObjectIDS(ctx, "dcim.devicetype")
	list, resp, err := s.client.APIClient.DcimAPI.DcimDeviceTypesList(ctx).Id(ids).Depth(10).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllDeviceTypes", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.DeviceType{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return []nb.DeviceType{}
	}

	return list.Results
}

func (s *DeviceTypeService) Update(ctx context.Context, id string, req nb.WritableDeviceTypeRequest) (*nb.DeviceType, error) {
	deviceType, resp, err := s.client.APIClient.DcimAPI.DcimDeviceTypesUpdate(ctx, id).WritableDeviceTypeRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateDeviceType", "failed to update UpdateDeviceType", "id", id, "model", req.GetModel(), "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated device type", "id", id, "model", deviceType.GetModel())
	return deviceType, nil
}

func (s *DeviceTypeService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.DcimAPI.DcimDeviceTypesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyDeviceType", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	return nil
}
