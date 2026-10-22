package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

// newTestLocationTypeSync returns a LocationTypeSync with just enough of a
// client to collect report lines. Service dependencies are left nil because
// these tests inject syncOne and prune directly.
func newTestLocationTypeSync() *LocationTypeSync {
	return &LocationTypeSync{
		client: &client.NautobotClient{Report: make(map[string][]string)},
	}
}

// TestApplyLocationTypes_OneBadItemDoesNotBlockTheRest verifies that a data
// error on one child location type does not prevent its sibling from being
// applied. The tree is:
//
//	root → good-child
//	     → bad-child  (Nautobot rejects with 400)
//
// Expected: root and good-child are applied, bad-child is noted as a
// PartialSyncError, and the prune step still runs.
func TestApplyLocationTypes_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestLocationTypeSync()

	root := models.LocationType{
		Name: "root",
		Children: []models.LocationType{
			{Name: "good-child"},
			{Name: "bad-child"},
		},
	}
	desired := models.LocationTypes{LocationType: []models.LocationType{root}}

	var applied []string
	syncOne := func(_ context.Context, lt models.LocationType, _ *string) (*string, error) {
		if lt.Name == "bad-child" {
			dataErr := syncerr.NewDataError(lt.Name, errors.New("400 Bad Request: location type cannot be applied"))
			return nil, errors.Join(errors.New("failed to sync location type "+lt.Name), dataErr)
		}
		applied = append(applied, lt.Name)
		id := lt.Name + "-id"
		return &id, nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.LocationTypes) { pruned = true }

	err := s.applyLocationTypes(context.Background(), desired, syncOne, prune)

	// root and good-child succeed; bad-child is skipped.
	if len(applied) != 2 || applied[0] != "root" || applied[1] != "good-child" {
		t.Errorf("expected root and good-child to be applied, got %v", applied)
	}
	// Prune still runs when there are only data failures.
	if !pruned {
		t.Error("expected deleteObsoleteLocationTypes to run on partial failure")
	}
	// The result is a PartialSyncError, not an infra abort.
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected a PartialSyncError, got %v", err)
	}
	if pe.Resource != "locationTypes" || len(pe.Failures) != 1 || pe.Failures[0].Item != "bad-child" {
		t.Errorf("unexpected partial error contents: %+v", pe)
	}
	// The failure is recorded in the client report.
	if len(s.client.Report["locationTypeDataError"]) != 1 {
		t.Errorf("expected one locationTypeDataError report line, got %v", s.client.Report["locationTypeDataError"])
	}
}

// TestApplyLocationTypes_InfraErrorAborts verifies that an infrastructure error
// stops the sync immediately, does not run the prune, and is returned as-is.
func TestApplyLocationTypes_InfraErrorAborts(t *testing.T) {
	s := newTestLocationTypeSync()
	desired := models.LocationTypes{LocationType: []models.LocationType{
		{Name: "a"},
		{Name: "b"},
		{Name: "c"},
	}}
	infra := errors.New("503 Service Unavailable")

	syncOne := func(_ context.Context, lt models.LocationType, _ *string) (*string, error) {
		if lt.Name == "b" {
			return nil, infra
		}
		id := lt.Name + "-id"
		return &id, nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.LocationTypes) { pruned = true }

	err := s.applyLocationTypes(context.Background(), desired, syncOne, prune)

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

// TestApplyLocationTypes_AllSuccess verifies that when every location type
// applies cleanly the sync returns nil, prune runs, and no report entries are
// recorded.
func TestApplyLocationTypes_AllSuccess(t *testing.T) {
	s := newTestLocationTypeSync()
	desired := models.LocationTypes{LocationType: []models.LocationType{
		{Name: "a", Children: []models.LocationType{{Name: "a1"}}},
		{Name: "b"},
	}}

	syncOne := func(_ context.Context, lt models.LocationType, _ *string) (*string, error) {
		id := lt.Name + "-id"
		return &id, nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.LocationTypes) { pruned = true }

	if err := s.applyLocationTypes(context.Background(), desired, syncOne, prune); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run on full success")
	}
	if len(s.client.Report) != 0 {
		t.Errorf("expected no report entries, got %v", s.client.Report)
	}
}
