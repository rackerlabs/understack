package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func newTestDeviceSync() *DeviceSync {
	return &DeviceSync{
		client: &client.NautobotClient{Report: make(map[string][]string)},
	}
}

func deviceList(names ...string) models.Devices {
	var ds models.Devices
	for _, n := range names {
		ds.Devices = append(ds.Devices, models.Device{Name: n})
	}
	return ds
}

func TestApplyDevices_OneBadItemDoesNotBlockTheRest(t *testing.T) {
	s := newTestDeviceSync()
	desired := deviceList("device-a", "device-bad", "device-c")

	var applied []string
	syncOne := func(_ context.Context, d models.Device) error {
		if d.Name == "device-bad" {
			dataErr := syncerr.NewDataError(d.Name, errors.New("400 Bad Request: device type not found"))
			return errors.Join(errors.New("failed to update device "+d.Name), dataErr)
		}
		applied = append(applied, d.Name)
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.Devices) { pruned = true }

	err := s.applyDevices(context.Background(), desired, syncOne, prune)

	if len(applied) != 2 || applied[0] != "device-a" || applied[1] != "device-c" {
		t.Errorf("expected the other devices to be applied, got %v", applied)
	}
	if !pruned {
		t.Error("expected deleteObsoleteDevices to run on a partial failure")
	}
	pe, ok := IsPartial(err)
	if !ok {
		t.Fatalf("expected a PartialSyncError, got %v", err)
	}
	if pe.Resource != "device" || len(pe.Failures) != 1 || pe.Failures[0].Item != "device-bad" {
		t.Errorf("unexpected partial error contents: %+v", pe)
	}
	if len(s.client.Report["deviceDataError"]) != 1 {
		t.Errorf("expected one deviceDataError report line, got %v", s.client.Report["deviceDataError"])
	}
}

func TestApplyDevices_InfraErrorAborts(t *testing.T) {
	s := newTestDeviceSync()
	desired := deviceList("a", "b", "c")
	infra := errors.New("500 Internal Server Error")

	syncOne := func(_ context.Context, d models.Device) error {
		if d.Name == "b" {
			return infra
		}
		return nil
	}

	pruned := false
	prune := func(_ context.Context, _ models.Devices) { pruned = true }

	err := s.applyDevices(context.Background(), desired, syncOne, prune)

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

func TestApplyDevices_AllSuccess(t *testing.T) {
	s := newTestDeviceSync()
	desired := deviceList("a", "b")

	syncOne := func(_ context.Context, _ models.Device) error { return nil }
	pruned := false
	prune := func(_ context.Context, _ models.Devices) { pruned = true }

	if err := s.applyDevices(context.Background(), desired, syncOne, prune); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !pruned {
		t.Error("expected prune to run on success")
	}
	if len(s.client.Report) != 0 {
		t.Errorf("expected no report entries, got %v", s.client.Report)
	}
}
