package helpers

import (
	"context"
	"net/http"

	"github.com/charmbracelet/log"
)

const defaultPageSize int32 = 1000

// PaginatedListCall represents a function that makes an API call with limit and offset.
// It returns the results for the current page, total count, the HTTP response, and any error.
type PaginatedListCall[T any] func(ctx context.Context, limit, offset int32) ([]T, int32, *http.Response, error)

// ReportFunc represents a function for reporting errors.
type ReportFunc func(key string, line ...string)

// PaginatedList fetches all results from a paginated API endpoint by iterating
// through pages using limit/offset until all items are collected.
//
// T: The type of objects being returned (e.g., nb.ConsolePortTemplate)
// ctx: The context for API calls
// apiCall: Function that makes the API call with limit and offset, returning (results, totalCount, response, error)
// reportFunc: Function to report errors
// operationName: Name of the operation for error reporting and logging
// additionalParams: Additional key-value parameters to include in error reports
func PaginatedList[T any](
	ctx context.Context,
	apiCall PaginatedListCall[T],
	reportFunc ReportFunc,
	operationName string,
	additionalParams ...string,
) []T {
	var allResults []T
	var offset int32

	for {
		results, totalCount, resp, err := apiCall(ctx, defaultPageSize, offset)
		if err != nil {
			bodyString := ReadResponseBody(resp)
			reportParams := []string{
				"failed to execute paginated API call",
				"operation", operationName,
				"error", err.Error(),
				"response_body", bodyString,
			}
			reportParams = append(reportParams, additionalParams...)
			reportFunc(operationName, reportParams...)
			return allResults
		}

		allResults = append(allResults, results...)

		// If we've collected all results or the page was empty, stop
		if int32(len(allResults)) >= totalCount || len(results) == 0 {
			break
		}

		offset += defaultPageSize
	}

	if len(allResults) == 0 {
		log.Info("no results found", "operation", operationName)
		return []T{}
	}

	log.Info("retrieved paginated results", "operation", operationName, "count", len(allResults))
	return allResults
}
