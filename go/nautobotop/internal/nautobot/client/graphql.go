package client

import (
	"context"
	"io"
	"net/http"

	"k8s.io/apimachinery/pkg/util/json"

	nb "github.com/nautobot/go-nautobot/v3"
)

type GraphQL struct {
	Data GraphQLData `json:"data"`
}

type ObjectChanges struct {
	ID              string `json:"id"`
	UserName        string `json:"user_name"`
	Action          string `json:"action"`
	RequestID       string `json:"request_id"`
	ChangedObjectID string `json:"changed_object_id"`
	RelatedObjectID string `json:"related_object_id"`
}

type GraphQLData struct {
	ObjectChanges []ObjectChanges `json:"object_changes"`
}

func (n *NautobotClient) GetCreateChangeList(ctx context.Context, objectType string) ([]ObjectChanges, *http.Response, error) {
	var allObjectChanges []ObjectChanges
	var lastResp *http.Response
	offset := 0
	limit := 100

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
				related_object_id
			}
			}`,
			Variables: map[string]any{
				"changedObjectType": objectType,
				"limit":             limit,
				"offset":            offset,
				"userName":          []string{n.Username},
				"action":            []string{"create", "delete"},
			},
		}

		_, resp, err := n.APIClient.GraphqlAPI.GraphqlCreate(ctx).
			GraphQLAPIRequest(req).
			Execute()
		if err != nil {
			return allObjectChanges, resp, err
		}

		lastResp = resp

		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			return allObjectChanges, resp, err
		}
		resp.Body.Close() //nolint:errcheck

		var graphQL GraphQL
		if err := json.Unmarshal(bodyBytes, &graphQL); err != nil {
			return allObjectChanges, resp, err
		}
		if len(graphQL.Data.ObjectChanges) == 0 {
			break
		}

		allObjectChanges = append(allObjectChanges, graphQL.Data.ObjectChanges...)
		offset += limit
	}

	return allObjectChanges, lastResp, nil
}
