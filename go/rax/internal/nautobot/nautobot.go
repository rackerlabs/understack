package nautobot

import (
	nb "github.com/nautobot/go-nautobot/v2"
)

// NautobotClient holds the Nautobot API client and configuration.
type NautobotClient struct {
	Config *nb.Configuration
	Client *nb.APIClient
}

// NautobotYAML defines the structure for loading Nautobot configuration from YAML.
type NautobotYAML struct {
	InstanceLocations []Location     `yaml:"instance_locations"`
	LocationTypes     []LocationType `yaml:"location_types"`
	RackGroup         []RackGroup    `yaml:"instance_rack_groups"`
	Rack              []Rack         `yaml:"instance_racks"`
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
	}
}
