package templates

import (
	"context"
	"net/http"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type ConsolePortTemplateService struct {
	client *client.NautobotClient
}

func NewConsolePortTemplateService(nautobotClient *client.NautobotClient) *ConsolePortTemplateService {
	return &ConsolePortTemplateService{
		client: nautobotClient,
	}
}

func (s *ConsolePortTemplateService) ListByDeviceType(ctx context.Context, deviceTypeID string) []nb.ConsolePortTemplate {
	ids := s.client.GetChangeObjectIDS(ctx, "dcim.consoleporttemplate", deviceTypeID)

	// Define the API call function for this specific endpoint
	apiCall := func(ctx context.Context, batchIds []string) ([]nb.ConsolePortTemplate, *http.Response, error) {
		list, resp, err := s.client.APIClient.DcimAPI.DcimConsolePortTemplatesList(ctx).Id(batchIds).Depth(2).DeviceType([]string{deviceTypeID}).Execute()
		if err != nil {
			return nil, resp, err
		}
		if list == nil {
			return []nb.ConsolePortTemplate{}, resp, nil
		}
		return list.Results, resp, nil
	}

	// Use the helper function for pagination
	return helpers.PaginatedListWithIDs(
		ctx,
		ids,
		apiCall,
		s.client.AddReport,
		"ListAllConsolePortTemplateByDeviceType",
		"device_type_id", deviceTypeID,
	)
}

func (s *ConsolePortTemplateService) GetByName(ctx context.Context, name, deviceTypeID string) nb.ConsolePortTemplate {
	list, resp, err := s.client.APIClient.DcimAPI.DcimConsolePortTemplatesList(ctx).Limit(10000).Depth(2).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetConsolePortTemplateByName", "failed to get console port template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return nb.ConsolePortTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Info("console port template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.ConsolePortTemplate{}
	}
	log.Info("found console port template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (s *ConsolePortTemplateService) Create(ctx context.Context, req nb.WritableConsolePortTemplateRequest) (*nb.ConsolePortTemplate, error) {
	consolePort, resp, err := s.client.APIClient.DcimAPI.DcimConsolePortTemplatesCreate(ctx).WritableConsolePortTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("CreateNewConsolePortTemplate", "failed to create console port template", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully created console port template", "name", consolePort.Name, "id", consolePort.Id)
	return consolePort, nil
}

func (s *ConsolePortTemplateService) Update(ctx context.Context, id string, req nb.WritableConsolePortTemplateRequest) (*nb.ConsolePortTemplate, error) {
	consolePort, resp, err := s.client.APIClient.DcimAPI.DcimConsolePortTemplatesUpdate(ctx, id).WritableConsolePortTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateConsolePortTemplate", "failed to update console port template", "id", id, "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated console port template", "id", id, "name", consolePort.Name)
	return consolePort, nil
}

func (s *ConsolePortTemplateService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.DcimAPI.DcimConsolePortTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyConsolePortTemplate", "failed to destroy console port template", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully destroyed console port template", "id", id)
	return err
}
