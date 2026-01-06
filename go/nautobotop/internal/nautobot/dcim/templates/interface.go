package templates

import (
	"context"
	"net/http"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type InterfaceTemplateService struct {
	client *client.NautobotClient
}

func NewInterfaceTemplateService(nautobotClient *client.NautobotClient) *InterfaceTemplateService {
	return &InterfaceTemplateService{
		client: nautobotClient,
	}
}

func (s *InterfaceTemplateService) ListByDeviceType(ctx context.Context, deviceTypeID string) []nb.InterfaceTemplate {
	ids := s.client.GetChangeObjectIDS(ctx, "dcim.interfacetemplate", deviceTypeID)

	// Define the API call function for this specific endpoint
	apiCall := func(ctx context.Context, batchIds []string) ([]nb.InterfaceTemplate, *http.Response, error) {
		list, resp, err := s.client.APIClient.DcimAPI.DcimInterfaceTemplatesList(ctx).Id(batchIds).Depth(2).DeviceType([]string{deviceTypeID}).Execute()
		if err != nil {
			return nil, resp, err
		}
		if list == nil {
			return []nb.InterfaceTemplate{}, resp, nil
		}
		return list.Results, resp, nil
	}
	return helpers.PaginatedListWithIDs(
		ctx,
		ids,
		apiCall,
		s.client.AddReport,
		"ListAllInterfaceTemplateByDeviceType",
		"device_type_id", deviceTypeID,
	)
}

func (s *InterfaceTemplateService) GetByName(ctx context.Context, name, deviceTypeID string) nb.InterfaceTemplate {
	list, resp, err := s.client.APIClient.DcimAPI.DcimInterfaceTemplatesList(ctx).Limit(10000).Depth(10).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetInterfaceTemplateByName", "failed to get interface template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
		return nb.InterfaceTemplate{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		log.Info("interface template not found", "name", name, "device_type_id", deviceTypeID)
		return nb.InterfaceTemplate{}
	}
	log.Info("found interface template", "name", name, "device_type_id", deviceTypeID, "id", list.Results[0].Id)
	return list.Results[0]
}

func (s *InterfaceTemplateService) Create(ctx context.Context, req nb.WritableInterfaceTemplateRequest) (*nb.InterfaceTemplate, error) {
	consolePort, resp, err := s.client.APIClient.DcimAPI.DcimInterfaceTemplatesCreate(ctx).WritableInterfaceTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("CreateNewInterfaceTemplate", "failed to create interface template", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully created interface template", "name", consolePort.Name, "id", consolePort.Id)
	return consolePort, nil
}

func (s *InterfaceTemplateService) Update(ctx context.Context, id string, req nb.WritableInterfaceTemplateRequest) (*nb.InterfaceTemplate, error) {
	consolePort, resp, err := s.client.APIClient.DcimAPI.DcimInterfaceTemplatesUpdate(ctx, id).WritableInterfaceTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateInterfaceTemplate", "failed to update interface template", "id", id, "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated interface template", "id", id, "name", consolePort.Name)
	return consolePort, nil
}

func (s *InterfaceTemplateService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.DcimAPI.DcimInterfaceTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyInterfaceTemplate", "failed to destroy interface template", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully destroyed interface template", "id", id)
	return err
}
