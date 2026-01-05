package templates

import (
	"context"
	"net/http"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type PowerPortTemplateService struct {
	client *client.NautobotClient
}

func NewPowerPortTemplateService(nautobotClient *client.NautobotClient) *PowerPortTemplateService {
	return &PowerPortTemplateService{
		client: nautobotClient,
	}
}

func (s *PowerPortTemplateService) ListByDeviceType(ctx context.Context, deviceTypeID string) []nb.PowerPortTemplate {
	ids := s.client.GetChangeObjectIDS(ctx, "dcim.powerporttemplate", deviceTypeID)

	// Define the API call function for this specific endpoint
	apiCall := func(ctx context.Context, batchIds []string) ([]nb.PowerPortTemplate, *http.Response, error) {
		list, resp, err := s.client.APIClient.DcimAPI.DcimPowerPortTemplatesList(ctx).Id(batchIds).Depth(2).DeviceType([]string{deviceTypeID}).Execute()
		if err != nil {
			return nil, resp, err
		}
		if list == nil {
			return []nb.PowerPortTemplate{}, resp, nil
		}
		return list.Results, resp, nil
	}

	// Use the helper function for pagination
	return helpers.PaginatedListWithIDs(
		ctx,
		ids,
		apiCall,
		s.client.AddReport,
		"ListAllPowerPortTemplate",
		"device_type_id", deviceTypeID,
	)
}

func (s *PowerPortTemplateService) GetByName(ctx context.Context, name, deviceTypeID string) nb.PowerPortTemplate {
	list, resp, err := s.client.APIClient.DcimAPI.DcimPowerPortTemplatesList(ctx).Limit(10000).Depth(2).Name([]string{name}).DeviceType([]string{deviceTypeID}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetPowerPortTemplateByName", "failed to get power port template by name", "name", name, "device_type_id", deviceTypeID, "error", err.Error(), "response_body", bodyString)
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
	powerPort, resp, err := s.client.APIClient.DcimAPI.DcimPowerPortTemplatesCreate(ctx).WritablePowerPortTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("CreateNewPowerPortTemplate", "failed to create power port template", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully created power port template", "name", powerPort.Name, "id", powerPort.Id)
	return powerPort, nil
}

func (s *PowerPortTemplateService) Update(ctx context.Context, id string, req nb.WritablePowerPortTemplateRequest) (*nb.PowerPortTemplate, error) {
	powerPort, resp, err := s.client.APIClient.DcimAPI.DcimPowerPortTemplatesUpdate(ctx, id).WritablePowerPortTemplateRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdatePowerPortTemplate", "failed to update power port template", "id", id, "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated power port template", "id", id, "name", powerPort.Name)
	return powerPort, nil
}

func (s *PowerPortTemplateService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.DcimAPI.DcimPowerPortTemplatesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyPowerPortTemplate", "failed to destroy power port template", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully destroyed power port template", "id", id)
	return nil
}
