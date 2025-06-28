package nautobot

import (
	"context"
	"fmt"
	"log"

	nb "github.com/nautobot/go-nautobot/v2"
)

// GetAllContentTypes retrieves all content types from Nautobot.
// It uses a default limit of 1000 and a depth of 1.
// Returns a slice of ContentType objects or nil if an error occurs.
func (n *NautobotClient) GetAllContentTypes(ctx context.Context) ([]nb.ContentType, error) {
	// Execute the API request to list content types.
	list, resp, err := n.Client.ExtrasAPI.ExtrasContentTypesList(ctx).
		Limit(1000).
		Depth(0).
		Execute()

	// Handle potential errors from the API request.
	if err != nil {
		// Log the error and the response body for debugging.
		log.Printf("error fetching content types: %v", err)
		logResponseBody(resp)
		return nil, fmt.Errorf("failed to list content types: %w", err)
	}

	// Check if results are present.
	if list == nil || list.Results == nil {
		log.Println("no content types found or results are nil.")
		return []nb.ContentType{}, nil // Return an empty slice instead of nil for no results.
	}

	return list.Results, nil
}
