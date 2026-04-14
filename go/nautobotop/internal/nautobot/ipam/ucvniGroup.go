package ipam

import (
	"context"
	"fmt"
	"io"
	"net/http"

	"github.com/charmbracelet/log"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"k8s.io/apimachinery/pkg/util/json"
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
	url := fmt.Sprintf("%s/plugins/undercloud-vni/ucvni-groups/?name=%s&depth=0&limit=1000&offset=0", baseURL, name)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		s.client.AddReport("GetUcvniGroupByName", "failed to create request", "name", name, "error", err.Error())
		return UcvniGroup{}
	}

	for key, value := range s.client.Config.DefaultHeader {
		req.Header.Set(key, value)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := s.client.Config.HTTPClient.Do(req)
	if err != nil {
		s.client.AddReport("GetUcvniGroupByName", "failed to get", "name", name, "error", err.Error())
		return UcvniGroup{}
	}
	defer resp.Body.Close() //nolint:errcheck

	if resp.StatusCode != http.StatusOK {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetUcvniGroupByName", "unexpected status code", "name", name, "status", fmt.Sprintf("%d", resp.StatusCode), "response_body", bodyString)
		return UcvniGroup{}
	}

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		s.client.AddReport("GetUcvniGroupByName", "failed to read response", "name", name, "error", err.Error())
		return UcvniGroup{}
	}

	var listResp ucvniGroupListResponse
	if err := json.Unmarshal(bodyBytes, &listResp); err != nil {
		s.client.AddReport("GetUcvniGroupByName", "failed to unmarshal response", "name", name, "error", err.Error())
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
