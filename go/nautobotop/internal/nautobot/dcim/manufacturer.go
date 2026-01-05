package dcim

import (
	"context"
	"log"
	"net/http"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type ManufacturerService struct {
	client *client.NautobotClient
}

func NewManufacturerService(nautobotClient *client.NautobotClient) *ManufacturerService {
	return &ManufacturerService{
		client: nautobotClient,
	}
}

func (s *ManufacturerService) ListAll(ctx context.Context) []nb.Manufacturer {
	ids := s.client.GetChangeObjectIDS(ctx, "dcim.manufacturer")

	// Define the API call function for this specific endpoint
	apiCall := func(ctx context.Context, batchIds []string) ([]nb.Manufacturer, *http.Response, error) {
		list, resp, err := s.client.APIClient.DcimAPI.DcimManufacturersList(ctx).Id(batchIds).Depth(10).Execute()
		if err != nil {
			return nil, resp, err
		}
		if list == nil {
			return []nb.Manufacturer{}, resp, nil
		}
		return list.Results, resp, nil
	}

	// Use the helper function for pagination
	return helpers.PaginatedListWithIDs(
		ctx,
		ids,
		apiCall,
		s.client.AddReport,
		"ListAllManufacturers",
	)
}

func (s *ManufacturerService) GetByName(ctx context.Context, name string) nb.Manufacturer {
	list, resp, err := s.client.APIClient.DcimAPI.DcimManufacturersList(ctx).Limit(10000).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetManufacturerByName", "failed to get manufacturer by name", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Manufacturer{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return nb.Manufacturer{}
	}
	return list.Results[0]
}

func (s *ManufacturerService) Create(ctx context.Context, req nb.ManufacturerRequest) (*nb.Manufacturer, error) {
	manufacture, resp, err := s.client.APIClient.DcimAPI.DcimManufacturersCreate(ctx).ManufacturerRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("CreateNewManufacturer", "failed to create manufacturer", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Printf("Created manufacture: %s", manufacture.Display)
	return manufacture, nil
}
