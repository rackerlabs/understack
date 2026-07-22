package admin

import (
	"context"
	"net/http"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type GroupService struct {
	client *client.NautobotClient
}

func NewGroupService(nautobotClient *client.NautobotClient) *GroupService {
	return &GroupService{
		client: nautobotClient,
	}
}

func (s *GroupService) Create(ctx context.Context, req nb.GroupRequest) (*nb.Group, error) {
	group, resp, err := s.client.APIClient.UsersAPI.UsersGroupsCreate(ctx).GroupRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewGroup", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateGroup", "created group", group.Name)
	return group, nil
}

func (s *GroupService) GetByName(ctx context.Context, name string) *nb.Group {
	list, resp, err := s.client.APIClient.UsersAPI.UsersGroupsList(ctx).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetGroupByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nil
	}
	if list == nil || len(list.Results) == 0 {
		return nil
	}
	return &list.Results[0]
}

func (s *GroupService) ListAll(ctx context.Context) []nb.Group {
	return helpers.PaginatedList(
		ctx,
		func(ctx context.Context, limit, offset int32) ([]nb.Group, int32, *http.Response, error) {
			list, resp, err := s.client.APIClient.UsersAPI.UsersGroupsList(ctx).
				Limit(limit).
				Offset(offset).
				Execute()
			if err != nil {
				return nil, 0, resp, err
			}
			if list == nil {
				return nil, 0, resp, nil
			}
			return list.Results, list.Count, resp, nil
		},
		s.client.AddReport,
		"ListAllGroups",
	)
}

// GetOrCreate fetches a group by name or creates it if it doesn't exist.
func (s *GroupService) GetOrCreate(ctx context.Context, name string) (*nb.Group, error) {
	existing := s.GetByName(ctx, name)
	if existing != nil {
		return existing, nil
	}

	log.Info("group not found, creating", "name", name)
	req := nb.GroupRequest{Name: name}
	return s.Create(ctx, req)
}
