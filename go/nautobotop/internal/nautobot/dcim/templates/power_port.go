package templates

import (
	"context"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type PowerPortTemplateService struct {
	client *nb.APIClient
	report func(key string, line ...string)
}

func NewPowerPortTemplateService(client *nb.APIClient, reportFunc func(key string, line ...string)) *PowerPortTemplateService {
	return &PowerPortTemplateService{
		client: client,
		report: reportFunc,
	}
}

func (s *PowerPortTemplateService) ListByDeviceType(ctx context.Context, deviceTypeID string) []nb.PowerPortTemplate {
	list, resp, err := s.client.DcimAPI.DcimPowerPortTemplatesList(ctx).Limit(10000).Depth(10).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("ListAllPowerPortTemplate", "failed to list power port templates", "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return []nb.PowerPortTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("no power port templates found", "device_type_id", deviceTypeID)
		return []nb.PowerPortTemplate{}
	}
	log.Debug("retrieved power port templates", "device_type_id", deviceTypeID, "count", len(list.Results))
	return list.Results
}

func (s *PowerPortTemplateService) GetByName(ctx context.Context, name, deviceTypeID string) nb.PowerPortTemplate {
	list, resp, err := s.client.DcimAPI.DcimPowerPortTemplatesList(ctx).Limit(10000).Depth(10).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("GetPowerPortTemplateByName", "failed to get power port template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return nb.PowerPortTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("power port template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.PowerPortTemplate{}
	}
	log.Debug("found power port template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (s *PowerPortTemplateService) Create(ctx context.Context, req nb.WritablePowerPortTemplateRequest) (*nb.PowerPortTemplate, error) {
	powerPort, resp, err := s.client.DcimAPI.DcimPowerPortTemplatesCreate(ctx).WritablePowerPortTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("CreateNewPowerPortTemplate", "failed to create power port template", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully created power port template", "name", powerPort.Name, "id", powerPort.Id)
	return powerPort, nil
}

func (s *PowerPortTemplateService) Update(ctx context.Context, id string, req nb.WritablePowerPortTemplateRequest) (*nb.PowerPortTemplate, error) {
	powerPort, resp, err := s.client.DcimAPI.DcimPowerPortTemplatesUpdate(ctx, id).WritablePowerPortTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("UpdatePowerPortTemplate", "failed to update power port template", "id", id, "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated power port template", "id", id, "name", powerPort.Name)
	return powerPort, nil
}

func (s *PowerPortTemplateService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.DcimAPI.DcimPowerPortTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("DestroyPowerPortTemplate", "failed to destroy power port template", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully destroyed power port template", "id", id)
	return nil
}
