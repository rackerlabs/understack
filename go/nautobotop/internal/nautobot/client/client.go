package client

import (
	"context"
	"fmt"
	"strings"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/samber/lo"
)

// NautobotClient holds the Nautobot API client and configuration.
type NautobotClient struct {
	Config    *nb.Configuration
	APIClient *nb.APIClient
	Username  string
	Report    map[string][]string
}

// AddReport appends one or more lines to the current reconciliation report.
func (n *NautobotClient) AddReport(key string, line ...string) {
	combined := strings.Join(line, " ")
	n.Report[key] = append(n.Report[key], combined)
	log.Error(key, combined)
}

// NewNautobotClient creates and configures a new Nautobot API client.
// apiURL: The base URL of the Nautobot API (e.g., "http://localhost:8000").
// authToken: The API token for authentication.
func NewNautobotClient(apiURL string, username, authToken string) *NautobotClient {
	config := nb.NewConfiguration()
	config.Servers = nb.ServerConfigurations{
		{
			URL: apiURL,
		},
	}
	// Add Authorization token header
	if authToken != "" {
		config.AddDefaultHeader("Authorization", fmt.Sprintf("Token %s", authToken))
	}
	client := nb.NewAPIClient(config)

	return &NautobotClient{
		Username:  username,
		Config:    config,
		APIClient: client,
		Report:    make(map[string][]string),
	}
}

// GetClient returns the Nautobot API client
func (n *NautobotClient) GetClient() *NautobotClient {
	return n
}

// GetChangeObjectIDS adapts GetCreateChangeList to the expected signature
// It filters out changed_object_id values where CREATE count equals DELETE count
// If relatedObjectID is provided, it filters ObjectChanges to only include those with matching RelatedObjectID
func (n *NautobotClient) GetChangeObjectIDS(ctx context.Context, objectType string, relatedObjectID ...string) []string {
	changes, _, err := n.GetCreateChangeList(ctx, objectType)
	if err != nil {
		return []string{}
	}

	// Filter by relatedObjectID if provided
	if len(relatedObjectID) != 0 {
		changes = lo.Filter(changes, func(change ObjectChanges, _ int) bool {
			return lo.Contains(relatedObjectID, change.RelatedObjectID)
		})
	}

	// Group changes by changed_object_id
	grouped := lo.GroupBy(changes, func(c ObjectChanges) string {
		return c.ChangedObjectID
	})

	// Filter and extract IDs where CREATE count does not equal DELETE count
	return lo.FilterMap(lo.Keys(grouped), func(id string, _ int) (string, bool) {
		createCount := lo.CountBy(grouped[id], func(c ObjectChanges) bool { return c.Action == "CREATE" })
		deleteCount := lo.CountBy(grouped[id], func(c ObjectChanges) bool { return c.Action == "DELETE" })
		return id, createCount != deleteCount
	})
}
