package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestRackSync() *RackSync {
	return &RackSync{client: &client.NautobotClient{Report: make(map[string][]string)}}
}

func rackList(names ...string) models.Racks {
	var rs models.Racks
	for _, n := range names {
		rs.Rack = append(rs.Rack, models.Rack{Name: n})
	}
	return rs
}

func TestApplyRacks_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestRackSync()
	desired := rackList("rack-a", "rack-bad", "rack-c")

	var applied []string
	syncOne := func(_ context.Context, r models.Rack) error {
		if r.Name == "rack-bad" {
			return errors.Join(errors.New("failed to update rack "+r.Name),
				syncerr.NewDataError(r.Name, errors.New("400 Bad Request")))
		}
		applied = append(applied, r.Name)
		return nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.Racks) { pruned = true }

	err := s.applyRacks(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "rack-a" || applied[1] != "rack-c" {
		t.Errorf("expected other racks applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "rack" || len(pe.Failures) != 1 || pe.Failures[0].Item != "rack-bad" {
		t.Errorf("unexpected partial error: %+v", pe)
	}
}

func TestApplyRacks_InfraErrorAborts(t *testing.T) {
	s := newTestRackSync()
	infra := errors.New("500 Internal Server Error")
	pruned := false
	err := s.applyRacks(context.Background(), rackList("a", "b", "c"),
		func(_ context.Context, r models.Rack) error {
			if r.Name == "b" {
				return infra
			}
			return nil
		},
		func(_ context.Context, _ models.Racks) { pruned = true },
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if pruned {
		t.Error("prune must not run on infra error")
	}
}

func TestApplyRacks_AllSuccess(t *testing.T) {
	s := newTestRackSync()
	pruned := false
	if err := s.applyRacks(context.Background(), rackList("a", "b"),
		func(_ context.Context, _ models.Rack) error { return nil },
		func(_ context.Context, _ models.Racks) { pruned = true },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
}
