package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestPrefixSync() *PrefixSync {
	return &PrefixSync{client: &client.NautobotClient{Report: make(map[string][]string)}}
}

func prefixList(prefixes ...string) models.Prefixes {
	var ps models.Prefixes
	for _, p := range prefixes {
		ps.Prefix = append(ps.Prefix, models.Prefix{Prefix: p})
	}
	return ps
}

// One bad prefix (400 from Nautobot) must not block the rest. Synced IDs from
// successful items are forwarded to prune; the bad item contributes no ID.
func TestApplyPrefixes_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestPrefixSync()
	desired := prefixList("10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12")

	var applied []string
	syncOne := func(_ context.Context, p models.Prefix) (string, error) {
		if p.Prefix == "192.168.0.0/16" {
			return "", errors.Join(
				errors.New("failed to update prefix "+p.Prefix),
				syncerr.NewDataError(p.Prefix, errors.New("400 Bad Request: invalid prefix")),
			)
		}
		applied = append(applied, p.Prefix)
		return "id-" + p.Prefix, nil
	}

	var prunedIDs map[string]struct{}
	prune := func(_ context.Context, ids map[string]struct{}) { prunedIDs = ids }

	err := s.applyPrefixes(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 {
		t.Errorf("expected 2 prefixes applied, got %v", applied)
	}
	if prunedIDs == nil {
		t.Fatal("expected prune to run")
	}
	// Only the two successful IDs are forwarded; the bad prefix contributes nothing.
	if len(prunedIDs) != 2 {
		t.Errorf("expected 2 synced IDs forwarded to prune, got %d: %v", len(prunedIDs), prunedIDs)
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "prefix" || len(pe.Failures) != 1 {
		t.Errorf("unexpected partial error: %+v", pe)
	}
}

func TestApplyPrefixes_InfraErrorAborts(t *testing.T) {
	s := newTestPrefixSync()
	infra := errors.New("500 Internal Server Error")
	var pruned bool
	err := s.applyPrefixes(context.Background(), prefixList("10.0.0.0/8", "192.168.0.0/16"),
		func(_ context.Context, p models.Prefix) (string, error) {
			if p.Prefix == "192.168.0.0/16" {
				return "", infra
			}
			return "id-" + p.Prefix, nil
		},
		func(_ context.Context, _ map[string]struct{}) { pruned = true },
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if pruned {
		t.Error("prune must not run on infra error")
	}
}

func TestApplyPrefixes_AllSuccess(t *testing.T) {
	s := newTestPrefixSync()
	var prunedIDs map[string]struct{}
	if err := s.applyPrefixes(context.Background(), prefixList("10.0.0.0/8", "172.16.0.0/12"),
		func(_ context.Context, p models.Prefix) (string, error) { return "id-" + p.Prefix, nil },
		func(_ context.Context, ids map[string]struct{}) { prunedIDs = ids },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(prunedIDs) != 2 {
		t.Errorf("expected 2 IDs forwarded to prune, got %d", len(prunedIDs))
	}
}
