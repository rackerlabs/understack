package helpers

import (
	"fmt"
	"io"
	"net/http"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
)

func BuildApprovalWorkflowStageResponseApprovalWorkflowStage(id string) nb.ApprovalWorkflowStageResponseApprovalWorkflowStage {
	return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{
		Id: &nb.ApprovalWorkflowApprovalWorkflowDefinitionId{
			String: &id,
		},
	}
}

func BuildNullableApprovalWorkflowUser(id string) nb.NullableApprovalWorkflowUser {
	user := nb.ApprovalWorkflowUser{
		Id: &nb.ApprovalWorkflowApprovalWorkflowDefinitionId{
			String: &id,
		},
	}
	return *nb.NewNullableApprovalWorkflowUser(&user)
}

func BuildNullableBulkWritableRackRequestRackGroup(id string) nb.NullableBulkWritableRackRequestRackGroup {
	rackGroup := nb.BulkWritableRackRequestRackGroup{
		Id: &nb.ApprovalWorkflowApprovalWorkflowDefinitionId{
			String: &id,
		},
	}
	return *nb.NewNullableBulkWritableRackRequestRackGroup(&rackGroup)
}

// ReadResponseBody safely reads and closes the response body.
// Returns the body content as a string. If resp is nil, returns empty string.
func ReadResponseBody(resp *http.Response) string {
	if resp == nil || resp.Body == nil {
		return "nil or empty body from remote"
	}
	defer func(Body io.ReadCloser) {
		err := Body.Close()
		if err != nil {
			log.Info("failed to close response body", "error", err)
		}
	}(resp.Body)

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Sprintf("failed to read response body: %v", err)
	}
	return string(bodyBytes)
}
