package admin

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	adminmodels "github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models/admin"
	syncp "github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/sync"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestPermissionGroupSync() *PermissionGroupSync {
	return &PermissionGroupSync{
		client: &client.NautobotClient{Report: make(map[string][]string)},
	}
}

func permissionList(names ...string) []adminmodels.Permission {
	perms := make([]adminmodels.Permission, 0, len(names))
	for _, n := range names {
		perms = append(perms, adminmodels.Permission{Name: n})
	}
	return perms
}

// One bad permission (400 from Nautobot) must not block the rest.
func TestApplyPermissionGroups_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestPermissionGroupSync()
	desired := permissionList("perm-a", "perm-bad", "perm-c")

	var applied []string
	syncOne := func(_ context.Context, perm adminmodels.Permission, _ map[string]int32) error {
		if perm.Name == "perm-bad" {
			return errors.Join(errors.New("failed to update permission "+perm.Name),
				syncerr.NewDataError(perm.Name, errors.New("400 Bad Request")))
		}
		applied = append(applied, perm.Name)
		return nil
	}

	err := s.applyPermissionGroups(context.Background(), desired, syncOne)

	if len(applied) != 2 || applied[0] != "perm-a" || applied[1] != "perm-c" {
		t.Errorf("expected other permissions applied, got %v", applied)
	}
	pe, ok := syncp.IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "permissionGroup" || len(pe.Failures) != 1 || pe.Failures[0].Item != "perm-bad" {
		t.Errorf("unexpected partial error: %+v", pe)
	}
	if len(s.client.Report["permissionGroupDataError"]) != 1 {
		t.Errorf("expected one permissionGroupDataError report line, got %v", s.client.Report["permissionGroupDataError"])
	}
}

func TestApplyPermissionGroups_InfraErrorAborts(t *testing.T) {
	s := newTestPermissionGroupSync()
	infra := errors.New("500 Internal Server Error")
	err := s.applyPermissionGroups(context.Background(), permissionList("a", "b", "c"),
		func(_ context.Context, perm adminmodels.Permission, _ map[string]int32) error {
			if perm.Name == "b" {
				return infra
			}
			return nil
		},
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if _, ok := syncp.IsPartial(err); ok {
		t.Error("infra error should not be a PartialSyncError")
	}
}

func TestApplyPermissionGroups_AllSuccess(t *testing.T) {
	s := newTestPermissionGroupSync()
	if err := s.applyPermissionGroups(context.Background(), permissionList("a", "b"),
		func(_ context.Context, _ adminmodels.Permission, _ map[string]int32) error { return nil },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(s.client.Report) != 0 {
		t.Errorf("expected no report entries, got %v", s.client.Report)
	}
}
