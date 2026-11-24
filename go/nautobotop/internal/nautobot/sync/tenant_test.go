package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestTenantSync() *TenantSync {
	return &TenantSync{client: &client.NautobotClient{Report: make(map[string][]string)}}
}

func tenantList(names ...string) models.Tenants {
	var ts models.Tenants
	for _, n := range names {
		ts.Tenant = append(ts.Tenant, models.Tenant{Name: n})
	}
	return ts
}

func TestApplyTenants_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestTenantSync()
	desired := tenantList("tenant-a", "tenant-bad", "tenant-c")

	var applied []string
	syncOne := func(_ context.Context, tenant models.Tenant) error {
		if tenant.Name == "tenant-bad" {
			return errors.Join(errors.New("failed to update tenant "+tenant.Name),
				syncerr.NewDataError(tenant.Name, errors.New("400 Bad Request")))
		}
		applied = append(applied, tenant.Name)
		return nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.Tenants) { pruned = true }

	err := s.applyTenants(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "tenant-a" || applied[1] != "tenant-c" {
		t.Errorf("expected other tenants applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "tenant" || len(pe.Failures) != 1 || pe.Failures[0].Item != "tenant-bad" {
		t.Errorf("unexpected partial error: %+v", pe)
	}
}

func TestApplyTenants_InfraErrorAborts(t *testing.T) {
	s := newTestTenantSync()
	infra := errors.New("500 Internal Server Error")
	pruned := false
	err := s.applyTenants(context.Background(), tenantList("a", "b", "c"),
		func(_ context.Context, tenant models.Tenant) error {
			if tenant.Name == "b" {
				return infra
			}
			return nil
		},
		func(_ context.Context, _ models.Tenants) { pruned = true },
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if pruned {
		t.Error("prune must not run on infra error")
	}
}

func TestApplyTenants_AllSuccess(t *testing.T) {
	s := newTestTenantSync()
	pruned := false
	if err := s.applyTenants(context.Background(), tenantList("a", "b"),
		func(_ context.Context, _ models.Tenant) error { return nil },
		func(_ context.Context, _ models.Tenants) { pruned = true },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
}
