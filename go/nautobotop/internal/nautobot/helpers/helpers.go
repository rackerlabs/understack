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

func BuildNullableBulkWritablePrefixRequestLocation(id string) nb.NullableBulkWritablePrefixRequestLocation {
	location := nb.BulkWritablePrefixRequestLocation{
		Id: &nb.ApprovalWorkflowApprovalWorkflowDefinitionId{
			String: &id,
		},
	}
	return *nb.NewNullableBulkWritablePrefixRequestLocation(&location)
}

func BuildNullableBulkWritablePrefixRequestRir(id string) nb.NullableBulkWritablePrefixRequestRir {
	rir := nb.BulkWritablePrefixRequestRir{
		Id: &nb.ApprovalWorkflowApprovalWorkflowDefinitionId{
			String: &id,
		},
	}
	return *nb.NewNullableBulkWritablePrefixRequestRir(&rir)
}

// BuildRelationshipSource builds a relationship value with the given object IDs on the source side.
func BuildRelationshipSource(ids ...string) nb.ApprovalWorkflowDefinitionRequestRelationshipsValue {
	objects := make([]nb.ApprovalWorkflowDefinitionRequestRelationshipsValueSourceObjectsInner, len(ids))
	for i, id := range ids {
		objects[i] = nb.ApprovalWorkflowDefinitionRequestRelationshipsValueSourceObjectsInner{Id: nb.PtrString(id)}
	}
	return nb.ApprovalWorkflowDefinitionRequestRelationshipsValue{
		Source: &nb.ApprovalWorkflowDefinitionRequestRelationshipsValueSource{
			Objects: objects,
		},
	}
}

// BuildRelationshipDestination builds a relationship value with the given object IDs on the destination side.
func BuildRelationshipDestination(ids ...string) nb.ApprovalWorkflowDefinitionRequestRelationshipsValue {
	objects := make([]nb.ApprovalWorkflowDefinitionRequestRelationshipsValueSourceObjectsInner, len(ids))
	for i, id := range ids {
		objects[i] = nb.ApprovalWorkflowDefinitionRequestRelationshipsValueSourceObjectsInner{Id: nb.PtrString(id)}
	}
	return nb.ApprovalWorkflowDefinitionRequestRelationshipsValue{
		Destination: &nb.ApprovalWorkflowDefinitionRequestRelationshipsValueSource{
			Objects: objects,
		},
	}
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
