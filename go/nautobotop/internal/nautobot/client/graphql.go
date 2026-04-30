package client

import (
	"context"
	"io"

	"k8s.io/apimachinery/pkg/util/json"

	nb "github.com/nautobot/go-nautobot/v3"
)

type GraphQL struct {
	Data GraphQLData `json:"data"`
}

type ObjectChanges struct {
	UserName string `json:"user_name"`
	Action   string `json:"action"`
}

type GraphQLData struct {
	ObjectChanges []ObjectChanges `json:"object_changes"`
}

// IsCreatedByUser checks if a specific object was created by the configured username.
func (n *NautobotClient) IsCreatedByUser(ctx context.Context, objectID string) (bool, error) {
	req := nb.GraphQLAPIRequest{
		Query: `
		query CheckObjectOwnership($changedObjectId: [String], $userName: [String]) {
		object_changes(
			changed_object_id: $changedObjectId
			user_name: $userName
            action__ic: ["CREATE"]
		) {
			user_name
			action
		}
		}`,
		Variables: map[string]any{
			"changedObjectId": []string{objectID},
			"userName":        []string{n.Username},
		},
	}

	_, resp, err := n.APIClient.GraphqlAPI.GraphqlCreate(ctx).
		GraphQLAPIRequest(req).
		Execute()
	if err != nil {
		return false, err
	}

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return false, err
	}
	resp.Body.Close() //nolint:errcheck

	var graphQL GraphQL
	if err := json.Unmarshal(bodyBytes, &graphQL); err != nil {
		return false, err
	}

	for _, change := range graphQL.Data.ObjectChanges {
		if change.Action == "CREATE" && change.UserName == n.Username {
			return true, nil
		}
	}
	return false, nil
}
