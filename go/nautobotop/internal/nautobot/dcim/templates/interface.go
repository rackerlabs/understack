package templates

import (
	"context"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type InterfaceTemplateService struct {
	client *nb.APIClient
	report func(key string, line ...string)
}

func NewInterfaceTemplateService(client *nb.APIClient, reportFunc func(key string, line ...string)) *InterfaceTemplateService {
	return &InterfaceTemplateService{
		client: client,
		report: reportFunc,
	}
}

func (s *InterfaceTemplateService) ListByDeviceType(ctx context.Context, deviceTypeID string) []nb.InterfaceTemplate {
	list, resp, err := s.client.DcimAPI.DcimInterfaceTemplatesList(ctx).Limit(10000).Depth(10).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("ListAllInterfaceTemplateByDeviceType", "failed to list interface templates", "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return []nb.InterfaceTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("no interface templates found", "device_type_id", deviceTypeID)
		return []nb.InterfaceTemplate{}
	}
	log.Debug("retrieved interface templates", "device_type_id", deviceTypeID, "count", len(list.Results))
	return list.Results
}

func (s *InterfaceTemplateService) GetByName(ctx context.Context, name, deviceTypeID string) nb.InterfaceTemplate {
	list, resp, err := s.client.DcimAPI.DcimInterfaceTemplatesList(ctx).Limit(10000).Depth(10).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("GetInterfaceTemplateByName", "failed to get interface template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return nb.InterfaceTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Debug("interface template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.InterfaceTemplate{}
	}
	log.Debug("found interface template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (s *InterfaceTemplateService) Create(ctx context.Context, req nb.WritableInterfaceTemplateRequest) (*nb.InterfaceTemplate, error) {
	consolePort, resp, err := s.client.DcimAPI.DcimInterfaceTemplatesCreate(ctx).WritableInterfaceTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("CreateNewInterfaceTemplate", "failed to create interface template", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully created interface template", "name", consolePort.Name, "id", consolePort.Id)
	return consolePort, nil
}

func (s *InterfaceTemplateService) Update(ctx context.Context, id string, req nb.WritableInterfaceTemplateRequest) (*nb.InterfaceTemplate, error) {
	consolePort, resp, err := s.client.DcimAPI.DcimInterfaceTemplatesUpdate(ctx, id).WritableInterfaceTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("UpdateInterfaceTemplate", "failed to update interface template", "id", id, "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated interface template", "id", id, "name", consolePort.Name)
	return consolePort, nil
}

func (s *InterfaceTemplateService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.DcimAPI.DcimInterfaceTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("DestroyInterfaceTemplate", "failed to destroy interface template", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully destroyed interface template", "id", id)
	return err
}
