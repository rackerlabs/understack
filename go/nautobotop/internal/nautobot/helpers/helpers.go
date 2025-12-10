package helpers

import (
	"context"
	"fmt"
	"strconv"

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

// PaginatedAPICall represents a function that makes an API call with a batch of IDs
type PaginatedAPICall[T any] func(ctx context.Context, ids []string) ([]T, *http.Response, error)

// ReportFunc represents a function for reporting errors
type ReportFunc func(key string, line ...string)

// PaginatedListWithIDs processes a list of IDs in batches and makes paginated API calls
// T: The type of objects being returned (e.g., nb.InterfaceTemplate)
// ids: List of IDs to process
// apiCall: Function that makes the API call with a batch of IDs
// reportFunc: Function to report errors
// operationName: Name of the operation for error reporting
// additionalParams: Additional parameters to include in error reports
func PaginatedListWithIDs[T any](
	ctx context.Context,
	ids []string,
	apiCall PaginatedAPICall[T],
	reportFunc ReportFunc,
	operationName string,
	additionalParams ...string,
) []T {
	if len(ids) == 0 {
		log.Info("no IDs found for operation", "operation", operationName)
		return []T{}
	}

	var allResults []T
	pageSize := 20

	// Process IDs in batches
	for i := 0; i < len(ids); i += pageSize {
		end := i + pageSize
		if end > len(ids) {
			end = len(ids)
		}

		batchIds := ids[i:end]
		results, resp, err := apiCall(ctx, batchIds)
		if err != nil {
			bodyString := ReadResponseBody(resp)
			batchNum := strconv.Itoa(i/pageSize + 1)

			// Build error report parameters
			reportParams := []string{
				"failed to execute paginated API call",
				"operation", operationName,
				"batch", batchNum,
				"error", err.Error(),
				"response_body", bodyString,
			}

			// Add additional parameters if provided
			reportParams = append(reportParams, additionalParams...)

			reportFunc(operationName, reportParams...)
			continue // Continue with next batch instead of returning empty
		}

		if len(results) > 0 {
			allResults = append(allResults, results...)
		}
	}

	if len(allResults) == 0 {
		log.Info("no results found", "operation", operationName)
		return []T{}
	}

	log.Info("retrieved paginated results", "operation", operationName, "count", len(allResults))
	return allResults
}
