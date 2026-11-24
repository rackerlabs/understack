package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

const (
	locBadChild  = "bad-child"
	locGoodChild = "good-child"
	locRoot      = "root"
)

// newTestLocationSync returns a LocationSync with just enough of a client to
// collect report lines. Service dependencies are left nil because these tests
// inject syncOne and prune directly.
func newTestLocationSync() *LocationSync {
	return &LocationSync{
		client: &client.NautobotClient{Report: make(map[string][]string)},
	}
}

// TestApplyLocations_OneBadItemDoesNotBlockTheRest verifies that a data error on
// one child location (e.g. a 400 from Nautobot) does not prevent its sibling
// from being applied. The tree is:
//
//	root → good-child
//	     → bad-child   (Nautobot rejects with 400)
//
// Expected: root and good-child are applied, bad-child is noted as a
// PartialSyncError, and the prune step still runs.
func TestApplyLocations_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestLocationSync()

	root := models.Location{
		Name: locRoot,
		Children: []models.Location{
			{Name: locGoodChild},
			{Name: locBadChild},
		},
	}
	desired := models.Locations{Location: []models.Location{root}}

	var applied []string
	syncOne := func(_ context.Context, loc models.Location, _ *string) (*string, error) {
		if loc.Name == locBadChild {
			dataErr := syncerr.NewDataError(loc.Name, errors.New("400 Bad Request: location cannot be applied"))
			return nil, errors.Join(errors.New("failed to sync location "+loc.Name), dataErr)
		}
		applied = append(applied, loc.Name)
		id := loc.Name + "-id"
		return &id, nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.Locations) { pruned = true }

	err := s.applyLocations(context.Background(), desired, syncOne, prune)

	// root and good-child succeed; bad-child is skipped.
	if len(applied) != 2 || applied[0] != locRoot || applied[1] != locGoodChild {
		t.Errorf("expected root and good-child to be applied, got %v", applied)
	}
	// Prune still runs when there are only data failures.
	if !pruned {
		t.Error("expected deleteObsoleteLocations to run on partial failure")
	}
	// The result is a PartialSyncError, not an infra abort.
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected a PartialSyncError, got %v", err)
	}
	if pe.Resource != "location" || len(pe.Failures) != 1 || pe.Failures[0].Item != locBadChild {
		t.Errorf("unexpected partial error contents: %+v", pe)
	}
	// The failure is recorded in the client report.
	if len(s.client.Report["locationDataError"]) != 1 {
		t.Errorf("expected one locationDataError report line, got %v", s.client.Report["locationDataError"])
	}
}

// TestApplyLocations_InfraErrorAborts verifies that an infrastructure error
// (auth, 5xx, transport) stops the sync immediately, does not run the prune,
// and is returned as-is (not wrapped in a PartialSyncError).
func TestApplyLocations_InfraErrorAborts(t *testing.T) {
	s := newTestLocationSync()
	desired := models.Locations{Location: []models.Location{
		{Name: "a"},
		{Name: "b"},
		{Name: "c"},
	}}
	infra := errors.New("503 Service Unavailable")

	syncOne := func(_ context.Context, loc models.Location, _ *string) (*string, error) {
		if loc.Name == "b" {
			return nil, infra // plain error — not a DataError → infrastructure
		}
		id := loc.Name + "-id"
		return &id, nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.Locations) { pruned = true }

	err := s.applyLocations(context.Background(), desired, syncOne, prune)

	if !errors.Is(err, infra) {
		t.Fatalf("expected the infrastructure error to be returned, got %v", err)
	}
	if _, ok := IsPartial(err); ok {
		t.Error("infrastructure error should not be a PartialSyncError")
	}
	if pruned {
		t.Error("prune must not run when the sync aborts on an infrastructure error")
	}
}

// TestApplyLocations_AllSuccess verifies that when every location applies
// cleanly the sync returns nil, prune runs, and no report entries are recorded.
func TestApplyLocations_AllSuccess(t *testing.T) {
	s := newTestLocationSync()
	desired := models.Locations{Location: []models.Location{
		{Name: "a", Children: []models.Location{{Name: "a1"}}},
		{Name: "b"},
	}}

	syncOne := func(_ context.Context, loc models.Location, _ *string) (*string, error) {
		id := loc.Name + "-id"
		return &id, nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.Locations) { pruned = true }

	if err := s.applyLocations(context.Background(), desired, syncOne, prune); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run on full success")
	}
	if len(s.client.Report) != 0 {
		t.Errorf("expected no report entries, got %v", s.client.Report)
	}
}
