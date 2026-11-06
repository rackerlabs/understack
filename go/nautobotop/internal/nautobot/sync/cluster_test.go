package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

// newTestClusterSync returns a ClusterSync with just enough of a client to
// collect report lines. The service dependencies are left nil because these
// tests inject the per-item sync and prune functions directly.
func newTestClusterSync() *ClusterSync {
	return &ClusterSync{
		client: &client.NautobotClient{Report: make(map[string][]string)},
	}
}

func clusterList(names ...string) models.Clusters {
	var cs models.Clusters
	for _, n := range names {
		cs.Cluster = append(cs.Cluster, models.Cluster{Name: n})
	}
	return cs
}

// One bad cluster (400 from Nautobot) must not block the rest, the prune must
// still run, and the result must surface as a PartialSyncError.
func TestApplyClusters_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestClusterSync()
	desired := clusterList("cluster-a", "cluster-bad", "cluster-c")

	var applied []string
	syncOne := func(_ context.Context, c models.Cluster) error {
		if c.Name == "cluster-bad" {
			dataErr := syncerr.NewDataError(c.Name, errors.New("400 Bad Request: cluster type 'unknown' not found"))
			return errors.Join(errors.New("failed to update cluster "+c.Name), dataErr)
		}
		applied = append(applied, c.Name)
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.Clusters) { pruned = true }

	err := s.applyClusters(context.Background(), desired, syncOne, prune)

	// The other two clusters are applied despite the bad one.
	if len(applied) != 2 || applied[0] != "cluster-a" || applied[1] != "cluster-c" {
		t.Errorf("expected the other clusters to be applied, got %v", applied)
	}
	// Prune still runs on a partial failure.
	if !pruned {
		t.Error("expected deleteObsoleteClusters to run on a partial failure")
	}
	// The failure surfaces as a PartialSyncError, not an infra abort.
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected a PartialSyncError, got %v", err)
	}
	if pe.Resource != "cluster" || len(pe.Failures) != 1 || pe.Failures[0].Item != "cluster-bad" {
		t.Errorf("unexpected partial error contents: %+v", pe)
	}
	// The failure is recorded in the client report for status/alerting.
	if len(s.client.Report["clusterDataError"]) != 1 {
		t.Errorf("expected one clusterDataError report line, got %v", s.client.Report["clusterDataError"])
	}
}

// An infrastructure error (auth, 5xx, transport) must stop the sync and must
// not run the prune, so controller-runtime backs off and retries.
func TestApplyClusters_InfraErrorAborts(t *testing.T) {
	s := newTestClusterSync()
	desired := clusterList("a", "b", "c")
	infra := errors.New("500 Internal Server Error")

	syncOne := func(_ context.Context, c models.Cluster) error {
		if c.Name == "b" {
			return infra // not a DataError -> infrastructure
		}
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.Clusters) { pruned = true }

	err := s.applyClusters(context.Background(), desired, syncOne, prune)

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

// When every cluster applies cleanly, the sync returns nil, prunes, and records
// no failures.
func TestApplyClusters_AllSuccess(t *testing.T) {
	s := newTestClusterSync()
	desired := clusterList("a", "b")

	syncOne := func(_ context.Context, _ models.Cluster) error { return nil }
	pruned := false
	prune := func(_ context.Context, _ models.Clusters) { pruned = true }

	if err := s.applyClusters(context.Background(), desired, syncOne, prune); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run on success")
	}
	if len(s.client.Report) != 0 {
		t.Errorf("expected no report entries, got %v", s.client.Report)
	}
}
