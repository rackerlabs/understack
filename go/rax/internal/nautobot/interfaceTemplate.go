package nautobot

import (
	"context"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
)

func (n *NautobotClient) ListAllInterfaceTemplateByDeviceType(ctx context.Context, deviceTypeID string) []nb.InterfaceTemplate {
	list, _, err := n.Client.DcimAPI.DcimInterfaceTemplatesList(ctx).Limit(10000).Depth(10).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		log.Error("failed to list console port templates", "device_type_id", deviceTypeID, "error", err)
		n.AddReport("ListAllInterfaceTemplateByDeviceType", "failed to list interface templates", "device_type_id", deviceTypeID, "error", err.Error())
		return []nb.InterfaceTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("no console port templates found", "device_type_id", deviceTypeID)
		return []nb.InterfaceTemplate{}
	}
	log.Debug("retrieved console port templates", "device_type_id", deviceTypeID, "count", len(list.Results))
	return list.Results
}

func (n *NautobotClient) GetInterfaceTemplateByName(ctx context.Context, name, deviceTypeID string) nb.InterfaceTemplate {
	list, _, err := n.Client.DcimAPI.DcimInterfaceTemplatesList(ctx).Limit(10000).Depth(10).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		log.Error("failed to get console port template by name", "name", name, "device_type_id", deviceTypeID, "error", err)
		n.AddReport("GetInterfaceTemplateByName", "failed to get interface template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error())
		return nb.InterfaceTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("console port template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.InterfaceTemplate{}
	}
	log.Debug("found console port template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (n *NautobotClient) CreateNewInterfaceTemplate(ctx context.Context, req nb.WritableInterfaceTemplateRequest) (*nb.InterfaceTemplate, error) {
	consolePort, _, err := n.Client.DcimAPI.DcimInterfaceTemplatesCreate(ctx).WritableInterfaceTemplateRequest(req).Execute()
	if err != nil {
		log.Error("failed to create console port template", "name", req.Name, "error", err)
		n.AddReport("CreateNewInterfaceTemplate", "failed to create interface template", "name", req.Name, "error", err.Error())
		return nil, err
	}
	log.Info("successfully created console port template", "name", consolePort.Name, "id", consolePort.Id)
	return consolePort, nil
}

func (n *NautobotClient) UpdateInterfaceTemplate(ctx context.Context, id string, req nb.WritableInterfaceTemplateRequest) (*nb.InterfaceTemplate, error) {
	consolePort, _, err := n.Client.DcimAPI.DcimInterfaceTemplatesUpdate(ctx, id).WritableInterfaceTemplateRequest(req).Execute()
	if err != nil {
		log.Error("failed to update console port template", "id", id, "name", req.Name, "error", err)
		n.AddReport("UpdateInterfaceTemplate", "failed to update interface template", "id", id, "name", req.Name, "error", err.Error())
		return nil, err
	}
	log.Info("successfully updated console port template", "id", id, "name", consolePort.Name)
	return consolePort, nil
}

func (n *NautobotClient) DestroyInterfaceTemplate(ctx context.Context, id string) error {
	_, err := n.Client.DcimAPI.DcimInterfaceTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		log.Error("failed to destroy console port template", "id", id, "error", err)
		n.AddReport("DestroyInterfaceTemplate", "failed to destroy interface template", "id", id, "error", err.Error())
		return err
	}
	log.Info("successfully destroyed console port template", "id", id)
	return err
}
