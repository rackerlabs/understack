package dcim

import (
	"context"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type DeviceTypeService struct {
	client              *nb.APIClient
	report              func(key string, line ...string)
	getCreateChangeList func(ctx context.Context, objectType string, username string) ([]interface{}, error)
}

func NewDeviceTypeService(client *nb.APIClient, reportFunc func(key string, line ...string), changeListFunc func(ctx context.Context, objectType string, username string) ([]interface{}, error)) *DeviceTypeService {
	return &DeviceTypeService{
		client:              client,
		report:              reportFunc,
		getCreateChangeList: changeListFunc,
	}
}

func (s *DeviceTypeService) Create(ctx context.Context, req nb.WritableDeviceTypeRequest) (*nb.DeviceType, error) {
	deviceType, resp, err := s.client.DcimAPI.DcimDeviceTypesCreate(ctx).WritableDeviceTypeRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("createNewDeviceType", "failed to create", "model", req.Model, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Printf("Created manufacture: %s", deviceType.Display)
	return deviceType, nil
}

func (s *DeviceTypeService) GetByName(ctx context.Context, name string) nb.DeviceType {
	list, resp, err := s.client.DcimAPI.DcimDeviceTypesList(ctx).Depth(10).Model([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("GetDeviceTypeByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.DeviceType{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return nb.DeviceType{}
	}
	return list.Results[0]
}

func (s *DeviceTypeService) ListAll(ctx context.Context, ids []string) []nb.DeviceType {
	list, resp, err := s.client.DcimAPI.DcimDeviceTypesList(ctx).Id(ids).Depth(10).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("ListAllDeviceTypes", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.DeviceType{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return []nb.DeviceType{}
	}

	return list.Results
}

func (s *DeviceTypeService) Update(ctx context.Context, id string, req nb.WritableDeviceTypeRequest) (*nb.DeviceType, error) {
	deviceType, resp, err := s.client.DcimAPI.DcimDeviceTypesUpdate(ctx, id).WritableDeviceTypeRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("UpdateDeviceType", "failed to update UpdateDeviceType", "id", id, "model", req.GetModel(), "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated device type", "id", id, "model", deviceType.GetModel())
	return deviceType, nil
}

func (s *DeviceTypeService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.DcimAPI.DcimDeviceTypesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("DestroyDeviceType", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	return nil
}
