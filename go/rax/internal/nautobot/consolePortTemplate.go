package nautobot

import (
	"context"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
)

func (n *NautobotClient) ListAllConsolePortTemplateByDeviceType(ctx context.Context, deviceTypeID string) []nb.ConsolePortTemplate {
	list, _, err := n.Client.DcimAPI.DcimConsolePortTemplatesList(ctx).Depth(10).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		log.Error("failed to list console port templates", "device_type_id", deviceTypeID, "error", err)
		return []nb.ConsolePortTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("no console port templates found", "device_type_id", deviceTypeID)
		return []nb.ConsolePortTemplate{}
	}
	log.Debug("retrieved console port templates", "device_type_id", deviceTypeID, "count", len(list.Results))
	return list.Results
}

func (n *NautobotClient) GetConsolePortTemplateByName(ctx context.Context, name, deviceTypeID string) nb.ConsolePortTemplate {
	list, _, err := n.Client.DcimAPI.DcimConsolePortTemplatesList(ctx).Depth(10).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		log.Error("failed to get console port template by name", "name", name, "device_type_id", deviceTypeID, "error", err)
		return nb.ConsolePortTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("console port template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.ConsolePortTemplate{}
	}
	log.Debug("found console port template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (n *NautobotClient) CreateNewConsolePortTemplate(ctx context.Context, req nb.WritableConsolePortTemplateRequest) (*nb.ConsolePortTemplate, error) {
	consolePort, _, err := n.Client.DcimAPI.DcimConsolePortTemplatesCreate(ctx).WritableConsolePortTemplateRequest(req).Execute()
	if err != nil {
		log.Error("failed to create console port template", "name", req.Name, "error", err)
		return nil, err
	}
	log.Info("successfully created console port template", "name", consolePort.Name, "id", consolePort.Id)
	return consolePort, nil
}

func (n *NautobotClient) UpdateConsolePortTemplate(ctx context.Context, id string, req nb.WritableConsolePortTemplateRequest) (*nb.ConsolePortTemplate, error) {
	consolePort, _, err := n.Client.DcimAPI.DcimConsolePortTemplatesUpdate(ctx, id).WritableConsolePortTemplateRequest(req).Execute()
	if err != nil {
		log.Error("failed to update console port template", "id", id, "name", req.Name, "error", err)
		return nil, err
	}
	log.Info("successfully updated console port template", "id", id, "name", consolePort.Name)
	return consolePort, nil
}

func (n *NautobotClient) DestroyConsolePortTemplate(ctx context.Context, id string) error {
	_, err := n.Client.DcimAPI.DcimConsolePortTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		log.Error("failed to destroy console port template", "id", id, "error", err)
		return err
	}
	log.Info("successfully destroyed console port template", "id", id)
	return err
}
