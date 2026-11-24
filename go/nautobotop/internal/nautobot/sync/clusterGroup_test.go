package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestClusterGroupSync() *ClusterGroupSync {
	return &ClusterGroupSync{
		client: &client.NautobotClient{Report: make(map[string][]string)},
	}
}

func clusterGroupList(names ...string) models.ClusterGroups {
	var cgs models.ClusterGroups
	for _, n := range names {
		cgs.ClusterGroup = append(cgs.ClusterGroup, models.ClusterGroup{Name: n})
	}
	return cgs
}

// One bad cluster group (400 from Nautobot) must not block the rest, the prune
// must still run, and the result must surface as a PartialSyncError.
func TestApplyClusterGroups_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestClusterGroupSync()
	desired := clusterGroupList("cg-a", "cg-bad", "cg-c")

	var applied []string
	syncOne := func(_ context.Context, cg models.ClusterGroup) error {
		if cg.Name == "cg-bad" {
			dataErr := syncerr.NewDataError(cg.Name, errors.New("400 Bad Request: invalid cluster group"))
			return errors.Join(errors.New("failed to update cluster group "+cg.Name), dataErr)
		}
		applied = append(applied, cg.Name)
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.ClusterGroups) { pruned = true }

	err := s.applyClusterGroups(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "cg-a" || applied[1] != "cg-c" {
		t.Errorf("expected the other cluster groups to be applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected deleteObsoleteClusterGroups to run on a partial failure")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected a PartialSyncError, got %v", err)
	}
	if pe.Resource != "clusterGroup" || len(pe.Failures) != 1 || pe.Failures[0].Item != "cg-bad" {
		t.Errorf("unexpected partial error contents: %+v", pe)
	}
	if len(s.client.Report["clusterGroupDataError"]) != 1 {
		t.Errorf("expected one clusterGroupDataError report line, got %v", s.client.Report["clusterGroupDataError"])
	}
}

func TestApplyClusterGroups_InfraErrorAborts(t *testing.T) {
	s := newTestClusterGroupSync()
	desired := clusterGroupList("a", "b", "c")
	infra := errors.New("500 Internal Server Error")

	syncOne := func(_ context.Context, cg models.ClusterGroup) error {
		if cg.Name == "b" {
			return infra
		}
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.ClusterGroups) { pruned = true }

	err := s.applyClusterGroups(context.Background(), desired, syncOne, prune)

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

func TestApplyClusterGroups_AllSuccess(t *testing.T) {
	s := newTestClusterGroupSync()
	desired := clusterGroupList("a", "b")

	syncOne := func(_ context.Context, _ models.ClusterGroup) error { return nil }
	pruned := false
	prune := func(_ context.Context, _ models.ClusterGroups) { pruned = true }

	if err := s.applyClusterGroups(context.Background(), desired, syncOne, prune); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run on success")
	}
	if len(s.client.Report) != 0 {
		t.Errorf("expected no report entries, got %v", s.client.Report)
	}
}
