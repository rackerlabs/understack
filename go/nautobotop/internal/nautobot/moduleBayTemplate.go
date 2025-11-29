package nautobot

import (
	"context"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
)

func (n *NautobotClient) ListAllModuleBayTemplateByDeviceType(ctx context.Context, deviceTypeID string) []nb.ModuleBayTemplate {
	list, resp, err := n.Client.DcimAPI.DcimModuleBayTemplatesList(ctx).Limit(10000).Depth(10).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("ListAllModuleBayTemplateByDeviceType", "failed to list module bay templates", "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return []nb.ModuleBayTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("no module bay templates found", "device_type_id", deviceTypeID)
		return []nb.ModuleBayTemplate{}
	}
	log.Debug("retrieved module bay templates", "device_type_id", deviceTypeID, "count", len(list.Results))
	return list.Results
}

func (n *NautobotClient) GetModuleBayTemplateByName(ctx context.Context, name, deviceTypeID string) nb.ModuleBayTemplate {
	list, resp, err := n.Client.DcimAPI.DcimModuleBayTemplatesList(ctx).Limit(10000).Depth(10).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("GetModuleBayTemplateByName", "failed to get module bay template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return nb.ModuleBayTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("module bay template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.ModuleBayTemplate{}
	}
	log.Debug("found module bay template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (n *NautobotClient) CreateNewModuleBayTemplate(ctx context.Context, req nb.ModuleBayTemplateRequest) (*nb.ModuleBayTemplate, error) {
	consolePort, resp, err := n.Client.DcimAPI.DcimModuleBayTemplatesCreate(ctx).ModuleBayTemplateRequest(req).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("CreateNewModuleBayTemplate", "failed to create module bay template", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully created module bay template", "name", consolePort.Name, "id", consolePort.Id)
	return consolePort, nil
}

func (n *NautobotClient) UpdateModuleBayTemplate(ctx context.Context, id string, req nb.ModuleBayTemplateRequest) (*nb.ModuleBayTemplate, error) {
	consolePort, resp, err := n.Client.DcimAPI.DcimModuleBayTemplatesUpdate(ctx, id).ModuleBayTemplateRequest(req).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("UpdateModuleBayTemplate", "failed to update module bay template", "id", id, "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated module bay template", "id", id, "name", consolePort.Name)
	return consolePort, nil
}

func (n *NautobotClient) DestroyModuleBayTemplate(ctx context.Context, id string) error {
	resp, err := n.Client.DcimAPI.DcimModuleBayTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("DestroyModuleBayTemplate", "failed to destroy module bay template", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully destroyed module bay template", "id", id)
	return err
}
