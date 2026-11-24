package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestTenantGroupSync() *TenantGroupSync {
	return &TenantGroupSync{client: &client.NautobotClient{Report: make(map[string][]string)}}
}

func tenantGroupList(names ...string) models.TenantGroups {
	var tgs models.TenantGroups
	for _, n := range names {
		tgs.TenantGroup = append(tgs.TenantGroup, models.TenantGroup{Name: n})
	}
	return tgs
}

func TestApplyTenantGroups_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestTenantGroupSync()
	desired := tenantGroupList("tg-a", "tg-bad", "tg-c")

	var applied []string
	syncOne := func(_ context.Context, tg models.TenantGroup) error {
		if tg.Name == "tg-bad" {
			return errors.Join(errors.New("failed to update tenant group "+tg.Name),
				syncerr.NewDataError(tg.Name, errors.New("400 Bad Request")))
		}
		applied = append(applied, tg.Name)
		return nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.TenantGroups) { pruned = true }

	err := s.applyTenantGroups(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "tg-a" || applied[1] != "tg-c" {
		t.Errorf("expected other tenant groups applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "tenantGroup" || len(pe.Failures) != 1 || pe.Failures[0].Item != "tg-bad" {
		t.Errorf("unexpected partial error: %+v", pe)
	}
}

func TestApplyTenantGroups_InfraErrorAborts(t *testing.T) {
	s := newTestTenantGroupSync()
	infra := errors.New("500 Internal Server Error")
	pruned := false
	err := s.applyTenantGroups(context.Background(), tenantGroupList("a", "b", "c"),
		func(_ context.Context, tg models.TenantGroup) error {
			if tg.Name == "b" {
				return infra
			}
			return nil
		},
		func(_ context.Context, _ models.TenantGroups) { pruned = true },
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if pruned {
		t.Error("prune must not run on infra error")
	}
}

func TestApplyTenantGroups_AllSuccess(t *testing.T) {
	s := newTestTenantGroupSync()
	pruned := false
	if err := s.applyTenantGroups(context.Background(), tenantGroupList("a", "b"),
		func(_ context.Context, _ models.TenantGroup) error { return nil },
		func(_ context.Context, _ models.TenantGroups) { pruned = true },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
}
