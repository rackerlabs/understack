package dcim

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type StatusService struct {
	client *client.NautobotClient
}

func NewStatusService(nautobotClient *client.NautobotClient) *StatusService {
	return &StatusService{
		client: nautobotClient,
	}
}

func (s *StatusService) GetByName(ctx context.Context, name string) nb.Status {
	list, resp, err := s.client.APIClient.ExtrasAPI.ExtrasStatusesList(ctx).Depth(1).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetLocationByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Status{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Status{}
	}
	if list.Results[0].Id == nil {
		return nb.Status{}
	}
	return list.Results[0]
}
