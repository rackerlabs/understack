package sync

import (
	"context"
	"errors"
	"strconv"

	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func optionalID(id string) *string {
	if id == "" {
		return nil
	}
	return nb.PtrString(id)
}

// ItemFailure records a single item that failed with a data error during a
// SyncAll. It is collected rather than aborting the whole sync so the remaining
// items still get applied.
type ItemFailure struct {
	// Item is a human-readable identifier for the offending item (e.g. the
	// VLAN group name), taken from the DataError when available.
	Item string
	// Err is the underlying data error.
	Err error
}

// SyncResult is the outcome of syncing a list of items. DataFailures holds the
// per-item data errors that were skipped so the caller can report them; it is
// empty when every item either succeeded or was unchanged.
type SyncResult struct {
	DataFailures []ItemFailure
}

// HasFailures reports whether any item was skipped due to a data error.
func (r SyncResult) HasFailures() bool { return len(r.DataFailures) > 0 }

// PartialSyncError is returned by a SyncAll when the desired state was applied
// except for one or more items that failed with data errors. It is distinct
// from an infrastructure error: the reconcile can continue to the next resource
// type, but the failed items need a human to fix the data, and this resource's
// SyncHash must not be advanced so it is retried next pass.
type PartialSyncError struct {
	Resource string
	Failures []ItemFailure
}

func (e *PartialSyncError) Error() string {
	return e.Resource + ": " + strconv.Itoa(len(e.Failures)) + " item(s) failed"
}

// IsPartial reports whether err is (or wraps) a PartialSyncError, and returns it.
func IsPartial(err error) (*PartialSyncError, bool) {
	var pe *PartialSyncError
	if errors.As(err, &pe) {
		return pe, true
	}
	return nil, false
}

// SyncItems applies syncOne to every item and isolates per-item data errors.
//
//   - On a data error (see Classify/DataError), the failure is recorded and the
//     loop continues to the next item. These do not abort the sync because they
//     will keep failing until a human fixes the input.
//   - On an infrastructure error (anything that is not a DataError), the loop
//     stops immediately and returns that error so the caller aborts and
//     controller-runtime backs off.
//
// The returned SyncResult carries the collected data failures; the returned
// error is non-nil only for an infrastructure failure.
func syncItems[T any](ctx context.Context, items []T, syncOne func(context.Context, T) error) (SyncResult, error) {
	return SyncItems(ctx, items, syncOne)
}

// SyncItems is the exported form of syncItems for use by sub-packages (e.g. admin).
func SyncItems[T any](ctx context.Context, items []T, syncOne func(context.Context, T) error) (SyncResult, error) {
	var result SyncResult
	for _, item := range items {
		err := syncOne(ctx, item)
		if err == nil {
			continue
		}
		var de *syncerr.DataError
		if errors.As(err, &de) {
			result.DataFailures = append(result.DataFailures, ItemFailure{Item: de.Item, Err: err})
			continue
		}
		// Infrastructure error: stop and surface it.
		return result, err
	}
	return result, nil
}
