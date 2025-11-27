package nautobot

import (
	"context"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
)

func (n *NautobotClient) ListAllPowerPortTemplate(ctx context.Context, deviceTypeID string) []nb.PowerPortTemplate {
	list, resp, err := n.Client.DcimAPI.DcimPowerPortTemplatesList(ctx).Limit(10000).Depth(10).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("ListAllPowerPortTemplate", "failed to list power port templates", "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return []nb.PowerPortTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("no power port templates found", "device_type_id", deviceTypeID)
		return []nb.PowerPortTemplate{}
	}
	log.Debug("retrieved power port templates", "device_type_id", deviceTypeID, "count", len(list.Results))
	return list.Results
}

func (n *NautobotClient) GetPowerPortTemplateByName(ctx context.Context, name, deviceTypeID string) nb.PowerPortTemplate {
	list, resp, err := n.Client.DcimAPI.DcimPowerPortTemplatesList(ctx).Limit(10000).Depth(10).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("GetPowerPortTemplateByName", "failed to get power port template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return nb.PowerPortTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("power port template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.PowerPortTemplate{}
	}
	log.Debug("found power port template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (n *NautobotClient) CreateNewPowerPortTemplate(ctx context.Context, req nb.WritablePowerPortTemplateRequest) (*nb.PowerPortTemplate, error) {
	powerPort, resp, err := n.Client.DcimAPI.DcimPowerPortTemplatesCreate(ctx).WritablePowerPortTemplateRequest(req).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("CreateNewPowerPortTemplate", "failed to create power port template", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully created power port template", "name", powerPort.Name, "id", powerPort.Id)
	return powerPort, nil
}

func (n *NautobotClient) UpdatePowerPortTemplate(ctx context.Context, id string, req nb.WritablePowerPortTemplateRequest) (*nb.PowerPortTemplate, error) {
	powerPort, resp, err := n.Client.DcimAPI.DcimPowerPortTemplatesUpdate(ctx, id).WritablePowerPortTemplateRequest(req).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("UpdatePowerPortTemplate", "failed to update power port template", "id", id, "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated power port template", "id", id, "name", powerPort.Name)
	return powerPort, nil
}

func (n *NautobotClient) DestroyPowerPortTemplate(ctx context.Context, id string) error {
	resp, err := n.Client.DcimAPI.DcimPowerPortTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("DestroyPowerPortTemplate", "failed to destroy power port template", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully destroyed power port template", "id", id)
	return nil
}
