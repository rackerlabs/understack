package nautobot

import (
	"context"
	"log"

	nb "github.com/nautobot/go-nautobot/v2"
)

func (n *NautobotClient) GetManufacturerByName(ctx context.Context, name string) nb.Manufacturer {
	list, resp, err := n.Client.DcimAPI.DcimManufacturersList(ctx).Limit(10000).Depth(10).Name([]string{name}).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("GetManufacturerByName", "failed to get manufacturer by name", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Manufacturer{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return nb.Manufacturer{}
	}
	return list.Results[0]
}

func (n *NautobotClient) CreateNewManufacturer(ctx context.Context, req nb.ManufacturerRequest) (*nb.Manufacturer, error) {
	manufacture, resp, err := n.Client.DcimAPI.DcimManufacturersCreate(ctx).ManufacturerRequest(req).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("CreateNewManufacturer", "failed to create manufacturer", "name", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Printf("Created manufacture: %s", manufacture.Display)
	return manufacture, nil
}
