package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestClusterTypeSync() *ClusterTypeSync {
	return &ClusterTypeSync{
		client: &client.NautobotClient{Report: make(map[string][]string)},
	}
}

func clusterTypeList(names ...string) models.ClusterTypes {
	var cts models.ClusterTypes
	for _, n := range names {
		cts.ClusterType = append(cts.ClusterType, models.ClusterType{Name: n})
	}
	return cts
}

func TestApplyClusterTypes_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestClusterTypeSync()
	desired := clusterTypeList("ct-a", "ct-bad", "ct-c")

	var applied []string
	syncOne := func(_ context.Context, ct models.ClusterType) error {
		if ct.Name == "ct-bad" {
			dataErr := syncerr.NewDataError(ct.Name, errors.New("400 Bad Request: invalid cluster type"))
			return errors.Join(errors.New("failed to update cluster type "+ct.Name), dataErr)
		}
		applied = append(applied, ct.Name)
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.ClusterTypes) { pruned = true }

	err := s.applyClusterTypes(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "ct-a" || applied[1] != "ct-c" {
		t.Errorf("expected the other cluster types to be applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected deleteObsoleteClusterTypes to run on a partial failure")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected a PartialSyncError, got %v", err)
	}
	if pe.Resource != "clusterType" || len(pe.Failures) != 1 || pe.Failures[0].Item != "ct-bad" {
		t.Errorf("unexpected partial error contents: %+v", pe)
	}
	if len(s.client.Report["clusterTypeDataError"]) != 1 {
		t.Errorf("expected one clusterTypeDataError report line, got %v", s.client.Report["clusterTypeDataError"])
	}
}

func TestApplyClusterTypes_InfraErrorAborts(t *testing.T) {
	s := newTestClusterTypeSync()
	desired := clusterTypeList("a", "b", "c")
	infra := errors.New("500 Internal Server Error")

	syncOne := func(_ context.Context, ct models.ClusterType) error {
		if ct.Name == "b" {
			return infra
		}
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.ClusterTypes) { pruned = true }

	err := s.applyClusterTypes(context.Background(), desired, syncOne, prune)

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

func TestApplyClusterTypes_AllSuccess(t *testing.T) {
	s := newTestClusterTypeSync()
	desired := clusterTypeList("a", "b")

	syncOne := func(_ context.Context, _ models.ClusterType) error { return nil }
	pruned := false
	prune := func(_ context.Context, _ models.ClusterTypes) { pruned = true }

	if err := s.applyClusterTypes(context.Background(), desired, syncOne, prune); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run on success")
	}
	if len(s.client.Report) != 0 {
		t.Errorf("expected no report entries, got %v", s.client.Report)
	}
}
