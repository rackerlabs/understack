// Package syncerr classifies errors that arise while syncing desired state into
// Nautobot as either data errors or infrastructure errors.
//
// It lives in its own leaf package so the low-level service packages (ipam,
// dcim, ...) can produce classified errors at the point where they still hold
// the *http.Response, without creating an import cycle with the higher-level
// sync package that consumes them.
package syncerr

import (
	"errors"
	"net/http"
)

// DataError marks a failure that is caused by the desired state itself rather
// than by the operator or its connection to Nautobot. A data error is specific
// to a single item (for example a VLAN group whose range change Nautobot
// rejects with a 400) and will keep failing until a human fixes the input, so
// retrying it is pointless. Item loops record a data error and move on to the
// next item instead of aborting the whole sync.
//
// Anything that is not a DataError is treated as an infrastructure error: a
// problem that is not tied to one item (auth failure, a 5xx from Nautobot, a
// transport error) where the operator cannot make progress and should stop so
// controller-runtime backs off and retries.
type DataError struct {
	// Item is a human-readable identifier for the offending item, e.g. the
	// VLAN group name. It is optional.
	Item string
	// Err is the underlying error.
	Err error
}

func (e *DataError) Error() string {
	if e.Item != "" {
		return e.Item + ": " + e.Err.Error()
	}
	return e.Err.Error()
}

func (e *DataError) Unwrap() error { return e.Err }

// NewDataError wraps err as a DataError for the given item.
func NewDataError(item string, err error) *DataError {
	return &DataError{Item: item, Err: err}
}

// IsDataError reports whether err is (or wraps) a DataError.
func IsDataError(err error) bool {
	var de *DataError
	return errors.As(err, &de)
}

// dataStatusCodes are the HTTP status codes we treat as data errors: the
// request reached Nautobot and was rejected because of the input, not because
// of a transient or infrastructure problem. Retrying the same input will not
// help until the data is fixed.
var dataStatusCodes = map[int]bool{
	http.StatusBadRequest:          true, // 400 - validation failure (the n11-21-network case)
	http.StatusNotFound:            true, // 404 - referenced object does not exist
	http.StatusConflict:            true, // 409 - conflicts with existing state
	http.StatusUnprocessableEntity: true, // 422 - semantically invalid input
}

// Classify decides whether err should be treated as a data error (per-item,
// not worth retrying) or an infrastructure error (stop and back off), using the
// HTTP response status code when one is available.
//
// It returns nil if err is nil. If the status code is one of dataStatusCodes it
// returns a *DataError tagged with item; otherwise (auth failure, 5xx, or no
// response at all, e.g. a transport error) it returns err unchanged so callers
// treat it as an infrastructure error.
func Classify(item string, err error, resp *http.Response) error {
	if err == nil {
		return nil
	}
	if resp != nil && dataStatusCodes[resp.StatusCode] {
		return NewDataError(item, err)
	}
	return err
}
