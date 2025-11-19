package nautobot

import (
	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"strings"
)

// NautobotClient holds the Nautobot API client and configuration.
type NautobotClient struct {
	Config *nb.Configuration
	Client *nb.APIClient
	Report map[string][]string
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

	// Example: To set a custom HTTP client with timeout (optional)
	// httpClient := &http.Client{
	// 	Timeout: 30 * time.Second,
	// }
	// config.HTTPClient = httpClient

	client := nb.NewAPIClient(config)

	return &NautobotClient{
		Config: config,
		Client: client,
		Report: make(map[string][]string),
	}
}
