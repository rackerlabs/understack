package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestDeviceTypeSync() *DeviceTypeSync {
	return &DeviceTypeSync{client: &client.NautobotClient{Report: make(map[string][]string)}}
}

func deviceTypeList(models_ ...string) models.DeviceTypes {
	var dts models.DeviceTypes
	for _, m := range models_ {
		dts.DeviceTypes = append(dts.DeviceTypes, models.DeviceType{Model: m})
	}
	return dts
}

func TestApplyDeviceTypes_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestDeviceTypeSync()
	desired := deviceTypeList("dt-a", "dt-bad", "dt-c")

	var applied []string
	syncOne := func(_ context.Context, dt models.DeviceType) error {
		if dt.Model == "dt-bad" {
			return errors.Join(errors.New("failed to update device type "+dt.Model),
				syncerr.NewDataError(dt.Model, errors.New("400 Bad Request")))
		}
		applied = append(applied, dt.Model)
		return nil
	}
	pruned := false
	prune := func(_ context.Context, _ models.DeviceTypes) { pruned = true }

	err := s.applyDeviceTypes(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "dt-a" || applied[1] != "dt-c" {
		t.Errorf("expected other device types applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected PartialSyncError, got %v", err)
	}
	if pe.Resource != "deviceType" || len(pe.Failures) != 1 || pe.Failures[0].Item != "dt-bad" {
		t.Errorf("unexpected partial error: %+v", pe)
	}
}

func TestApplyDeviceTypes_InfraErrorAborts(t *testing.T) {
	s := newTestDeviceTypeSync()
	infra := errors.New("500 Internal Server Error")
	pruned := false
	err := s.applyDeviceTypes(context.Background(), deviceTypeList("a", "b", "c"),
		func(_ context.Context, dt models.DeviceType) error {
			if dt.Model == "b" {
				return infra
			}
			return nil
		},
		func(_ context.Context, _ models.DeviceTypes) { pruned = true },
	)
	if !errors.Is(err, infra) {
		t.Fatalf("expected infra error, got %v", err)
	}
	if pruned {
		t.Error("prune must not run on infra error")
	}
}

func TestApplyDeviceTypes_AllSuccess(t *testing.T) {
	s := newTestDeviceTypeSync()
	pruned := false
	if err := s.applyDeviceTypes(context.Background(), deviceTypeList("a", "b"),
		func(_ context.Context, _ models.DeviceType) error { return nil },
		func(_ context.Context, _ models.DeviceTypes) { pruned = true },
	); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run")
	}
}
