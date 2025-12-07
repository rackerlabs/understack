package nautobot

import (
	"context"
	"strings"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim/templates"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/sync"
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
	config.Servers = nb.ServerConfigurations{
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

// SyncAllDeviceTypes synchronizes device types from YAML data to Nautobot
func (n *NautobotClient) SyncAllDeviceTypes(ctx context.Context, data map[string]string) error {
	manufacturerSvc := dcim.NewManufacturerService(n.Client, n.AddReport)
	deviceTypeSvc := dcim.NewDeviceTypeService(n.Client, n.AddReport, n.getCreateChangeListWrapper)
	consolePortSvc := templates.NewConsolePortTemplateService(n.Client, n.AddReport)
	powerPortSvc := templates.NewPowerPortTemplateService(n.Client, n.AddReport)
	interfaceSvc := templates.NewInterfaceTemplateService(n.Client, n.AddReport)
	moduleBaySvc := templates.NewModuleBayTemplateService(n.Client, n.AddReport)

	syncSvc := sync.NewDeviceTypeSync(
		manufacturerSvc,
		deviceTypeSvc,
		consolePortSvc,
		powerPortSvc,
		interfaceSvc,
		moduleBaySvc,
		n.getCreateChangeListWrapper,
		n.AddReport,
	)

	return syncSvc.SyncAll(ctx, data)
}

// getCreateChangeListWrapper adapts GetCreateChangeList to the expected signature
func (n *NautobotClient) getCreateChangeListWrapper(ctx context.Context, objectType string, username string) ([]any, error) {
	changes, _, err := n.GetCreateChangeList(ctx, objectType, username)
	if err != nil {
		return nil, err
	}

	result := make([]any, len(changes))
	for i, change := range changes {
		result[i] = change
	}
	return result, nil
}
