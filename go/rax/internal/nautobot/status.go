package nautobot

import (
	"context"
	"log"

	nb "github.com/nautobot/go-nautobot/v2"
)

// FindStatusID retrieves the ID of a status by its name via an API call.
// Returns an empty string if the status is not found or if an error occurs.
func (n *NautobotClient) FindStatus(ctx context.Context, name string) nb.Status {
	list, _, err := n.Client.ExtrasAPI.ExtrasStatusesList(ctx).Depth(0).Name([]string{name}).Execute()
	if err != nil {
		log.Printf("failed to fetch status by name '%s': %v", name, err)
		return nb.Status{}
	}

	if list == nil || list.Results == nil || len(list.Results) == 0 {
		log.Printf("status with name '%s' not found.", name) // Optional: log if not found
		return nb.Status{}
	}

	return list.Results[0]
}
