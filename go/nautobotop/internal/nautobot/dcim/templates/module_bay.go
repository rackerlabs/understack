package templates

import (
	"context"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type ModuleBayTemplateService struct {
	client *nb.APIClient
	report func(key string, line ...string)
}

func NewModuleBayTemplateService(client *nb.APIClient, reportFunc func(key string, line ...string)) *ModuleBayTemplateService {
	return &ModuleBayTemplateService{
		client: client,
		report: reportFunc,
	}
}

func (s *ModuleBayTemplateService) ListByDeviceType(ctx context.Context, deviceTypeID string) []nb.ModuleBayTemplate {
	list, resp, err := s.client.DcimAPI.DcimModuleBayTemplatesList(ctx).Limit(10000).Depth(10).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("ListAllModuleBayTemplateByDeviceType", "failed to list module bay templates", "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return []nb.ModuleBayTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("no module bay templates found", "device_type_id", deviceTypeID)
		return []nb.ModuleBayTemplate{}
	}
	log.Debug("retrieved module bay templates", "device_type_id", deviceTypeID, "count", len(list.Results))
	return list.Results
}

func (s *ModuleBayTemplateService) GetByName(ctx context.Context, name, deviceTypeID string) nb.ModuleBayTemplate {
	list, resp, err := s.client.DcimAPI.DcimModuleBayTemplatesList(ctx).Limit(10000).Depth(10).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("GetModuleBayTemplateByName", "failed to get module bay template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return nb.ModuleBayTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("module bay template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.ModuleBayTemplate{}
	}
	log.Debug("found module bay template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (s *ModuleBayTemplateService) Create(ctx context.Context, req nb.ModuleBayTemplateRequest) (*nb.ModuleBayTemplate, error) {
	consolePort, resp, err := s.client.DcimAPI.DcimModuleBayTemplatesCreate(ctx).ModuleBayTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("CreateNewModuleBayTemplate", "failed to create module bay template", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully created module bay template", "name", consolePort.Name, "id", consolePort.Id)
	return consolePort, nil
}

func (s *ModuleBayTemplateService) Update(ctx context.Context, id string, req nb.ModuleBayTemplateRequest) (*nb.ModuleBayTemplate, error) {
	consolePort, resp, err := s.client.DcimAPI.DcimModuleBayTemplatesUpdate(ctx, id).ModuleBayTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("UpdateModuleBayTemplate", "failed to update module bay template", "id", id, "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated module bay template", "id", id, "name", consolePort.Name)
	return consolePort, nil
}

func (s *ModuleBayTemplateService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.DcimAPI.DcimModuleBayTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("DestroyModuleBayTemplate", "failed to destroy module bay template", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully destroyed module bay template", "id", id)
	return err
}
