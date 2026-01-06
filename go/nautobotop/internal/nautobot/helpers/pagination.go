package helpers

import (
	"context"
	"net/http"
	"strconv"

	"github.com/charmbracelet/log"
)

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
		end := min(i+pageSize, len(ids))

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
