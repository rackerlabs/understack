package client

import (
	"context"
	"encoding/json"
	"fmt"
)

type tokenListResponse struct {
	Count   int           `json:"count"`
	Results []tokenResult `json:"results"`
}

type tokenResult struct {
	User tokenUser `json:"user"`
}

type tokenUser struct {
	Username string `json:"username"`
}

// ResolveUsername fetches the username associated with the configured API token
// from Nautobot's /api/users/tokens/ endpoint and stores it in n.Username.
func (n *NautobotClient) ResolveUsername(ctx context.Context) error {
	url := fmt.Sprintf("%s/users/tokens/", n.apiURL)
	resp, err := n.reqClient.R().SetContext(ctx).Get(url)
	if err != nil {
		return fmt.Errorf("failed to call users/tokens API: %w", err)
	}
	if resp.StatusCode != 200 {
		return fmt.Errorf("users/tokens API returned status %d", resp.StatusCode)
	}

	var result tokenListResponse
	if err := json.Unmarshal(resp.Bytes(), &result); err != nil {
		return fmt.Errorf("failed to parse users/tokens response: %w", err)
	}
	if result.Count == 0 || len(result.Results) == 0 {
		return fmt.Errorf("users/tokens API returned no tokens")
	}

	n.Username = result.Results[0].User.Username
	return nil
}
