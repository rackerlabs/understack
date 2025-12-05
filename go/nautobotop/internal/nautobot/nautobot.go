package nautobot

import (
	"context"
	"io"
	"net/http"
	"strings"

	"k8s.io/apimachinery/pkg/util/json"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
)

// NautobotClient holds the Nautobot API client and configuration.
type NautobotClient struct {
	Config *nb.Configuration
	Client *nb.APIClient
	Report map[string][]string
}

type GraphQL struct {
	Data GraphQLData `json:"data"`
}
type ObjectChanges struct {
	ID              string `json:"id"`
	UserName        string `json:"user_name"`
	Action          string `json:"action"`
	RequestID       string `json:"request_id"`
	ChangedObjectID string `json:"changed_object_id"`
}
type GraphQLData struct {
	ObjectChanges []ObjectChanges `json:"object_changes"`
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
func NewNautobotClient(apiURL string, authToken string) *NautobotClient {
	config := nb.NewConfiguration()
	config.Servers = nb.ServerConfigurations{ // A more structured way to define servers
		{
			URL: apiURL,
		},
	}

	// Add Authorization token header
	if authToken != "" {
		config.AddDefaultHeader("Authorization", "Token "+authToken)
	}

	client := nb.NewAPIClient(config)

	return &NautobotClient{
		Config: config,
		Client: client,
		Report: make(map[string][]string),
	}
}

func (n *NautobotClient) GetCreateChangeList(ctx context.Context, objectType string, username string) ([]ObjectChanges, *http.Response, error) {
	var allObjectChanges []ObjectChanges
	var lastResp *http.Response
	offset := 0
	limit := 100000

	for {
		req := nb.GraphQLAPIRequest{
			Query: `
			query GetObjectChanges($changedObjectType: String, $userName: [String], $action: [String], $limit: Int, $offset: Int) {
			object_changes(
				changed_object_type: $changedObjectType
				user_name: $userName
				action: $action
				limit: $limit
				offset: $offset
			) {
				id
				user_name
				action
				request_id
				changed_object_id
			}
			}`,
			Variables: map[string]interface{}{
				"changedObjectType": objectType,
				"limit":             limit,
				"offset":            offset,
				"userName":          []string{username},
				"action":            []string{"create"},
			},
		}

		_, resp, err := n.Client.GraphqlAPI.GraphqlCreate(ctx).
			GraphQLAPIRequest(req).
			Execute()
		if err != nil {
			return allObjectChanges, resp, err
		}

		lastResp = resp

		// Read the response body
		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			return allObjectChanges, resp, err
		}
		resp.Body.Close()

		// Unmarshal the body into GraphQL struct
		var graphQL GraphQL
		if err := json.Unmarshal(bodyBytes, &graphQL); err != nil {
			return allObjectChanges, resp, err
		}

		// If no results, break the loop
		if len(graphQL.Data.ObjectChanges) == 0 {
			break
		}

		// Append results to the collection
		allObjectChanges = append(allObjectChanges, graphQL.Data.ObjectChanges...)

		// Increment offset for next iteration
		offset += limit
	}

	return allObjectChanges, lastResp, nil
}
