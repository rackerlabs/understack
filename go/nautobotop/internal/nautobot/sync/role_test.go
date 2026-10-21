package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestRoleSync() *RoleSync {
	return &RoleSync{client: &client.NautobotClient{Report: make(map[string][]string)}}
}

func roleList(names ...string) models.Roles {
	var rs models.Roles
	for _, n := range names {
		rs.Role = append(rs.Role, models.Role{Name: n})
	}
	return rs
}

func TestApplyRoles_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestRoleSync()
	desired := roleList("role-a", "role-bad", "role-c")

	var applied []string
	syncOne := func(_ context.Context, r models.Role) error {
		if r.Name == "role-bad" {
			return errors.Join(errors.New("failed to update role "+r.Name),
				syncerr.NewDataError(r.Name, errors.New("400 Bad Request")))
		}
		applied = append(applied, r.Name)
		return nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.Roles) { pruned = true }

	err := s.applyRoles(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "role-a" || applied[1] != "role-c" {
		t.Errorf("expected other roles applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "role" || len(pe.Failures) != 1 || pe.Failures[0].Item != "role-bad" {
		t.Errorf("unexpected partial error: %+v", pe)
	}
}

func TestApplyRoles_InfraErrorAborts(t *testing.T) {
	s := newTestRoleSync()
	infra := errors.New("500 Internal Server Error")
	pruned := false
	err := s.applyRoles(context.Background(), roleList("a", "b", "c"),
		func(_ context.Context, r models.Role) error {
			if r.Name == "b" {
				return infra
			}
			return nil
		},
		func(_ context.Context, _ models.Roles) { pruned = true },
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if pruned {
		t.Error("prune must not run on infra error")
	}
}

func TestApplyRoles_AllSuccess(t *testing.T) {
	s := newTestRoleSync()
	pruned := false
	if err := s.applyRoles(context.Background(), roleList("a", "b"),
		func(_ context.Context, _ models.Role) error { return nil },
		func(_ context.Context, _ models.Roles) { pruned = true },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
}
