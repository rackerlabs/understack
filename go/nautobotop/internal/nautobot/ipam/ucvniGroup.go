package ipam

import (
	"context"
	"fmt"
	"net/http"

	"github.com/charmbracelet/log"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
)

// UcvniGroup represents a UCVNI group from the undercloud-vni plugin API.
type UcvniGroup struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type ucvniGroupListResponse struct {
	Results []UcvniGroup `json:"results"`
}

type UcvniGroupService struct {
	client *client.NautobotClient
}

func NewUcvniGroupService(nautobotClient *client.NautobotClient) *UcvniGroupService {
	return &UcvniGroupService{
		client: nautobotClient,
	}
}

// GetByName looks up a UCVNI group by name
func (s *UcvniGroupService) GetByName(ctx context.Context, name string) UcvniGroup {
	if group, ok := cache.FindByName(s.client.Cache, "ucvnigroups", name, func(g UcvniGroup) string {
		return g.Name
	}); ok {
		return group
	}

	baseURL := s.client.Config.Servers[0].URL

	var listResp ucvniGroupListResponse
	resp, err := s.client.ReqClient.R().
		SetContext(ctx).
		SetHeaders(s.client.Config.DefaultHeader).
		SetQueryParams(map[string]string{
			"name":   name,
			"depth":  "0",
			"limit":  "1000",
			"offset": "0",
		}).
		SetSuccessResult(&listResp).
		Get(baseURL + "/plugins/undercloud-vni/ucvni-groups/")
	if err != nil {
		s.client.AddReport("GetUcvniGroupByName", "failed to get", "name", name, "error", err.Error())
		return UcvniGroup{}
	}
	if resp.StatusCode != http.StatusOK {
		s.client.AddReport("GetUcvniGroupByName", "unexpected status code", "name", name, "status", fmt.Sprintf("%d", resp.StatusCode), "response_body", resp.String())
		return UcvniGroup{}
	}

	if len(listResp.Results) == 0 {
		return UcvniGroup{}
	}

	group := listResp.Results[0]
	cache.AddToCollection(s.client.Cache, "ucvnigroups", group)
	log.Info("GetUcvniGroupByName", "found ucvni group", group.Name, "id", group.ID)

	return group
}
