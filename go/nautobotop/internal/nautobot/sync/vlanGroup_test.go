package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

// newTestVlanGroupSync returns a VlanGroupSync with just enough of a client to
// collect report lines. The service dependencies are left nil because these
// tests inject the per-item sync and prune functions directly.
func newTestVlanGroupSync() *VlanGroupSync {
	return &VlanGroupSync{
		client: &client.NautobotClient{Report: make(map[string][]string)},
	}
}

func vlanGroupList(names ...string) models.VlanGroups {
	var vgs models.VlanGroups
	for _, n := range names {
		vgs.VlanGroup = append(vgs.VlanGroup, models.VlanGroup{Name: n})
	}
	return vgs
}

// This reproduces the production incident: Nautobot rejects the n11-21-network
// vlan group with a 400 while the others are fine. The bad group must not block
// the rest, the prune must still run, and the sync must report a partial
// failure (not an infrastructure abort).
func TestApplyVlanGroups_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestVlanGroupSync()
	desired := vlanGroupList("n11-19-network", "n11-21-network", "n11-23-network")

	var applied []string
	syncOne := func(_ context.Context, vg models.VlanGroup) error {
		if vg.Name == "n11-21-network" {
			// Mirror the real path: ipam classifies the 400 as a data error,
			// then the sync layer wraps it the way updateVlanGroup does.
			dataErr := syncerr.NewDataError(vg.Name, errors.New("400 Bad Request: VLAN group range may not be re-sized due to existing VLANs (IDs: 4010)"))
			return errors.Join(errors.New("failed to update vlan group "+vg.Name), dataErr)
		}
		applied = append(applied, vg.Name)
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.VlanGroups) { pruned = true }

	err := s.applyVlanGroups(context.Background(), desired, syncOne, prune)

	// The other two groups are applied despite the bad one.
	if len(applied) != 2 || applied[0] != "n11-19-network" || applied[1] != "n11-23-network" {
		t.Errorf("expected the other groups to be applied, got %v", applied)
	}
	// Prune still runs on a partial failure.
	if !pruned {
		t.Error("expected deleteObsoleteVlanGroups to run on a partial failure")
	}
	// The failure surfaces as a PartialSyncError, not an infra abort.
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected a PartialSyncError, got %v", err)
	}
	if pe.Resource != "vlanGroup" || len(pe.Failures) != 1 || pe.Failures[0].Item != "n11-21-network" {
		t.Errorf("unexpected partial error contents: %+v", pe)
	}
	// The failure is recorded in the client report for status/alerting.
	if len(s.client.Report["vlanGroupDataError"]) != 1 {
		t.Errorf("expected one vlanGroupDataError report line, got %v", s.client.Report["vlanGroupDataError"])
	}
}

// An infrastructure error (auth, 5xx, transport) must stop the sync and must
// not run the prune, so controller-runtime backs off and retries.
func TestApplyVlanGroups_InfraErrorAborts(t *testing.T) {
	s := newTestVlanGroupSync()
	desired := vlanGroupList("a", "b", "c")
	infra := errors.New("401 Unauthorized")

	syncOne := func(_ context.Context, vg models.VlanGroup) error {
		if vg.Name == "b" {
			return infra // not a DataError -> infrastructure
		}
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.VlanGroups) { pruned = true }

	err := s.applyVlanGroups(context.Background(), desired, syncOne, prune)

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

// When every group applies cleanly, the sync returns nil, prunes, and records
// no failures.
func TestApplyVlanGroups_AllSuccess(t *testing.T) {
	s := newTestVlanGroupSync()
	desired := vlanGroupList("a", "b")

	syncOne := func(_ context.Context, _ models.VlanGroup) error { return nil }
	pruned := false
	prune := func(_ context.Context, _ models.VlanGroups) { pruned = true }

	if err := s.applyVlanGroups(context.Background(), desired, syncOne, prune); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run on success")
	}
	if len(s.client.Report) != 0 {
		t.Errorf("expected no report entries, got %v", s.client.Report)
	}
}
