package nautobot

import (
	"context"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
)

func (n *NautobotClient) ListAllDeviceBayTemplateByDeviceType(ctx context.Context, deviceTypeID string) []nb.DeviceBayTemplate {
	list, _, err := n.Client.DcimAPI.DcimDeviceBayTemplatesList(ctx).Depth(10).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		log.Error("failed to list device bay templates", "device_type_id", deviceTypeID, "error", err)
		return []nb.DeviceBayTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("no device bay templates found", "device_type_id", deviceTypeID)
		return []nb.DeviceBayTemplate{}
	}
	log.Debug("retrieved device bay templates", "device_type_id", deviceTypeID, "count", len(list.Results))
	return list.Results
}

func (n *NautobotClient) GetDeviceBayTemplateByName(ctx context.Context, name, deviceTypeID string) nb.DeviceBayTemplate {
	list, _, err := n.Client.DcimAPI.DcimDeviceBayTemplatesList(ctx).Depth(10).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		log.Error("failed to get device bay template by name", "name", name, "device_type_id", deviceTypeID, "error", err)
		return nb.DeviceBayTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("device bay template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.DeviceBayTemplate{}
	}
	log.Debug("found device bay template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (n *NautobotClient) CreateNewDeviceBayTemplate(ctx context.Context, req nb.DeviceBayTemplateRequest) (*nb.DeviceBayTemplate, error) {
	consolePort, _, err := n.Client.DcimAPI.DcimDeviceBayTemplatesCreate(ctx).DeviceBayTemplateRequest(req).Execute()
	if err != nil {
		log.Error("failed to create device bay template", "name", req.Name, "error", err)
		return nil, err
	}
	log.Info("successfully created device bay template", "name", consolePort.Name, "id", consolePort.Id)
	return consolePort, nil
}

func (n *NautobotClient) UpdateDeviceBayTemplate(ctx context.Context, id string, req nb.DeviceBayTemplateRequest) (*nb.DeviceBayTemplate, error) {
	consolePort, _, err := n.Client.DcimAPI.DcimDeviceBayTemplatesUpdate(ctx, id).DeviceBayTemplateRequest(req).Execute()
	if err != nil {
		log.Error("failed to update device bay template", "id", id, "name", req.Name, "error", err)
		return nil, err
	}
	log.Info("successfully updated device bay template", "id", id, "name", consolePort.Name)
	return consolePort, nil
}

func (n *NautobotClient) DestroyDeviceBayTemplate(ctx context.Context, id string) error {
	_, err := n.Client.DcimAPI.DcimDeviceBayTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		log.Error("failed to destroy device bay template", "id", id, "error", err)
		return err
	}
	log.Info("successfully destroyed device bay template", "id", id)
	return err
}
