package helpers

import (
	"fmt"
	"io"
	"net/http"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
)

func BuildBulkWritableCableRequestStatus(uuid string) *nb.BulkWritableCableRequestStatus {
	return &nb.BulkWritableCableRequestStatus{
		Id: &nb.BulkWritableCableRequestStatusId{
			String: nb.PtrString(uuid),
		},
	}
}

func BuildNullableBulkWritableCircuitRequestTenant(uuid string) nb.NullableBulkWritableCircuitRequestTenant {
	return *nb.NewNullableBulkWritableCircuitRequestTenant(&nb.BulkWritableCircuitRequestTenant{
		Id: &nb.BulkWritableCableRequestStatusId{
			String: nb.PtrString(uuid),
		},
	})
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
