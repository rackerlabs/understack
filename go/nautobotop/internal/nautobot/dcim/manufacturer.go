package dcim

import (
	"context"
	"log"

	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type ManufacturerService struct {
	client *nb.APIClient
	report func(key string, line ...string)
}

func NewManufacturerService(client *nb.APIClient, reportFunc func(key string, line ...string)) *ManufacturerService {
	return &ManufacturerService{
		client: client,
		report: reportFunc,
	}
}

func (s *ManufacturerService) GetByName(ctx context.Context, name string) nb.Manufacturer {
	list, resp, err := s.client.DcimAPI.DcimManufacturersList(ctx).Limit(10000).Depth(10).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("GetManufacturerByName", "failed to get manufacturer by name", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Manufacturer{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return nb.Manufacturer{}
	}
	return list.Results[0]
}

func (s *ManufacturerService) Create(ctx context.Context, req nb.ManufacturerRequest) (*nb.Manufacturer, error) {
	manufacture, resp, err := s.client.DcimAPI.DcimManufacturersCreate(ctx).ManufacturerRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.report("CreateNewManufacturer", "failed to create manufacturer", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Printf("Created manufacture: %s", manufacture.Display)
	return manufacture, nil
}
