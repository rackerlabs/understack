package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestNamespaceSync() *NamespaceSync {
	return &NamespaceSync{client: &client.NautobotClient{Report: make(map[string][]string)}}
}

func namespaceList(names ...string) models.Namespaces {
	var ns models.Namespaces
	for _, n := range names {
		ns.Namespace = append(ns.Namespace, models.Namespace{Name: n})
	}
	return ns
}

func TestApplyNamespaces_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestNamespaceSync()
	desired := namespaceList("ns-a", "ns-bad", "ns-c")

	var applied []string
	syncOne := func(_ context.Context, ns models.Namespace) error {
		if ns.Name == "ns-bad" {
			return errors.Join(errors.New("failed to update namespace "+ns.Name),
				syncerr.NewDataError(ns.Name, errors.New("400 Bad Request")))
		}
		applied = append(applied, ns.Name)
		return nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.Namespaces) { pruned = true }

	err := s.applyNamespaces(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "ns-a" || applied[1] != "ns-c" {
		t.Errorf("expected other namespaces applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "namespace" || len(pe.Failures) != 1 || pe.Failures[0].Item != "ns-bad" {
		t.Errorf("unexpected partial error: %+v", pe)
	}
}

func TestApplyNamespaces_InfraErrorAborts(t *testing.T) {
	s := newTestNamespaceSync()
	desired := namespaceList("a", "b", "c")
	infra := errors.New("500 Internal Server Error")
	pruned := false
	err := s.applyNamespaces(context.Background(), desired,
		func(_ context.Context, ns models.Namespace) error {
			if ns.Name == "b" {
				return infra
			}
			return nil
		},
		func(_ context.Context, _ models.Namespaces) { pruned = true },
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if pruned {
		t.Error("prune must not run on infra error")
	}
}

func TestApplyNamespaces_AllSuccess(t *testing.T) {
	s := newTestNamespaceSync()
	pruned := false
	if err := s.applyNamespaces(context.Background(), namespaceList("a", "b"),
		func(_ context.Context, _ models.Namespace) error { return nil },
		func(_ context.Context, _ models.Namespaces) { pruned = true },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
}
