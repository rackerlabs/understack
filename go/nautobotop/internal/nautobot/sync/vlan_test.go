package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestVlanSync() *VlanSync {
	return &VlanSync{client: &client.NautobotClient{Report: make(map[string][]string)}}
}

func vlanList(names ...string) models.Vlans {
	var vs models.Vlans
	for _, n := range names {
		vs.Vlan = append(vs.Vlan, models.Vlan{Name: n})
	}
	return vs
}

func TestApplyVlans_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestVlanSync()
	desired := vlanList("vlan-a", "vlan-bad", "vlan-c")

	var applied []string
	syncOne := func(_ context.Context, v models.Vlan) error {
		if v.Name == "vlan-bad" {
			return errors.Join(errors.New("failed to update vlan "+v.Name),
				syncerr.NewDataError(v.Name, errors.New("400 Bad Request")))
		}
		applied = append(applied, v.Name)
		return nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.Vlans) { pruned = true }

	err := s.applyVlans(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "vlan-a" || applied[1] != "vlan-c" {
		t.Errorf("expected other vlans applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "vlan" || len(pe.Failures) != 1 || pe.Failures[0].Item != "vlan-bad" {
		t.Errorf("unexpected partial error: %+v", pe)
	}
}

func TestApplyVlans_InfraErrorAborts(t *testing.T) {
	s := newTestVlanSync()
	infra := errors.New("500 Internal Server Error")
	pruned := false
	err := s.applyVlans(context.Background(), vlanList("a", "b", "c"),
		func(_ context.Context, v models.Vlan) error {
			if v.Name == "b" {
				return infra
			}
			return nil
		},
		func(_ context.Context, _ models.Vlans) { pruned = true },
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if pruned {
		t.Error("prune must not run on infra error")
	}
}

func TestApplyVlans_AllSuccess(t *testing.T) {
	s := newTestVlanSync()
	pruned := false
	if err := s.applyVlans(context.Background(), vlanList("a", "b"),
		func(_ context.Context, _ models.Vlan) error { return nil },
		func(_ context.Context, _ models.Vlans) { pruned = true },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
}
