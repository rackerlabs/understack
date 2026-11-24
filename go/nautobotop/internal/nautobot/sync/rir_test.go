package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestRirSync() *RirSync {
	return &RirSync{client: &client.NautobotClient{Report: make(map[string][]string)}}
}

func rirList(names ...string) models.Rirs {
	var rs models.Rirs
	for _, n := range names {
		rs.Rir = append(rs.Rir, models.Rir{Name: n})
	}
	return rs
}

func TestApplyRirs_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestRirSync()
	desired := rirList("rir-a", "rir-bad", "rir-c")

	var applied []string
	syncOne := func(_ context.Context, r models.Rir) error {
		if r.Name == "rir-bad" {
			return errors.Join(errors.New("failed to update rir "+r.Name),
				syncerr.NewDataError(r.Name, errors.New("400 Bad Request")))
		}
		applied = append(applied, r.Name)
		return nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.Rirs) { pruned = true }

	err := s.applyRirs(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "rir-a" || applied[1] != "rir-c" {
		t.Errorf("expected other rirs applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "rir" || len(pe.Failures) != 1 || pe.Failures[0].Item != "rir-bad" {
		t.Errorf("unexpected partial error: %+v", pe)
	}
}

func TestApplyRirs_InfraErrorAborts(t *testing.T) {
	s := newTestRirSync()
	infra := errors.New("500 Internal Server Error")
	pruned := false
	err := s.applyRirs(context.Background(), rirList("a", "b", "c"),
		func(_ context.Context, r models.Rir) error {
			if r.Name == "b" {
				return infra
			}
			return nil
		},
		func(_ context.Context, _ models.Rirs) { pruned = true },
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if pruned {
		t.Error("prune must not run on infra error")
	}
}

func TestApplyRirs_AllSuccess(t *testing.T) {
	s := newTestRirSync()
	pruned := false
	if err := s.applyRirs(context.Background(), rirList("a", "b"),
		func(_ context.Context, _ models.Rir) error { return nil },
		func(_ context.Context, _ models.Rirs) { pruned = true },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
}
