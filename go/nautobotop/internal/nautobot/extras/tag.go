package extras

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type TagService struct {
	client *client.NautobotClient
}

func NewTagService(nautobotClient *client.NautobotClient) *TagService {
	return &TagService{
		client: nautobotClient,
	}
}

func (s *TagService) GetByName(ctx context.Context, name string) nb.Tag {
	if tag, ok := cache.FindByName(s.client.Cache, "tags", name, func(t nb.Tag) string {
		return t.Name
	}); ok {
		return tag
	}

	list, resp, err := s.client.APIClient.ExtrasAPI.ExtrasTagsList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetTagByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Tag{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Tag{}
	}
	if list.Results[0].Id == nil {
		return nb.Tag{}
	}

	return list.Results[0]
}
