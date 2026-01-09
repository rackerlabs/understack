package templates

import (
	"context"
	"net/http"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type ModuleBayTemplateService struct {
	client *client.NautobotClient
}

func NewModuleBayTemplateService(nautobotClient *client.NautobotClient) *ModuleBayTemplateService {
	return &ModuleBayTemplateService{
		client: nautobotClient,
	}
}

func (s *ModuleBayTemplateService) ListByDeviceType(ctx context.Context, deviceTypeID string) []nb.ModuleBayTemplate {
	ids := s.client.GetChangeObjectIDS(ctx, "dcim.modulebaytemplate", deviceTypeID)

	// Define the API call function for this specific endpoint
	apiCall := func(ctx context.Context, batchIds []string) ([]nb.ModuleBayTemplate, *http.Response, error) {
		list, resp, err := s.client.APIClient.DcimAPI.DcimModuleBayTemplatesList(ctx).Id(batchIds).Depth(2).DeviceType([]string{deviceTypeID}).Execute()
		if err != nil {
			return nil, resp, err
		}
		if list == nil {
			return []nb.ModuleBayTemplate{}, resp, nil
		}
		return list.Results, resp, nil
	}

	// Use the helper function for pagination
	return helpers.PaginatedListWithIDs(
		ctx,
		ids,
		apiCall,
		s.client.AddReport,
		"ListAllModuleBayTemplateByDeviceType",
		"device_type_id", deviceTypeID,
	)
}

func (s *ModuleBayTemplateService) GetByName(ctx context.Context, name, deviceTypeID string) nb.ModuleBayTemplate {
	list, resp, err := s.client.APIClient.DcimAPI.DcimModuleBayTemplatesList(ctx).Limit(10000).Depth(2).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetModuleBayTemplateByName", "failed to get module bay template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return nb.ModuleBayTemplate{}
	}
	if list == nil || len(list.Results) == 0 {
		log.Info("module bay template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.ModuleBayTemplate{}
	}
	if list.Results[0].Id == nil {
		log.Info("module bay template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.ModuleBayTemplate{}
	}
	log.Info("found module bay template", "name", name, "device_type_id", deviceTypeID, "id", *list.Results[0].Id)
	return list.Results[0]
}

func (s *ModuleBayTemplateService) Create(ctx context.Context, req nb.ModuleBayTemplateRequest) (*nb.ModuleBayTemplate, error) {
	consolePort, resp, err := s.client.APIClient.DcimAPI.DcimModuleBayTemplatesCreate(ctx).ModuleBayTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("CreateNewModuleBayTemplate", "failed to create module bay template", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully created module bay template", "name", consolePort.Name, "id", consolePort.Id)
	return consolePort, nil
}

func (s *ModuleBayTemplateService) Update(ctx context.Context, id string, req nb.ModuleBayTemplateRequest) (*nb.ModuleBayTemplate, error) {
	consolePort, resp, err := s.client.APIClient.DcimAPI.DcimModuleBayTemplatesUpdate(ctx, id).ModuleBayTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateModuleBayTemplate", "failed to update module bay template", "id", id, "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated module bay template", "id", id, "name", consolePort.Name)
	return consolePort, nil
}

func (s *ModuleBayTemplateService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.DcimAPI.DcimModuleBayTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyModuleBayTemplate", "failed to destroy module bay template", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully destroyed module bay template", "id", id)
	return err
}
