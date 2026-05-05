package server

import (
	"testing"
	"time"

	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
)

func findFamily(families []MetricFamily, name string) *MetricFamily {
	for i := range families {
		if families[i].Name == name {
			return &families[i]
		}
	}
	return nil
}

func findLabel(labels []Label, name string) string {
	for _, l := range labels {
		if l.Name == name {
			return l.Value
		}
	}
	return ""
}

func TestTransform_LastSeen(t *testing.T) {
	ts := time.Unix(1776287267, 0)
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {NodeUUID: "uuid-1", NodeName: "Dell-Test", LastSeen: ts},
	}
	families := Transform(nodes)
	f := findFamily(families, "ironic_node_last_seen_timestamp_seconds")
	if f == nil || len(f.Samples) != 1 {
		t.Fatal("expected one last_seen sample")
	}
	if f.Samples[0].Value != float64(ts.Unix()) {
		t.Errorf("unexpected value: %v", f.Samples[0].Value)
	}
}

func TestTransform_SkipsZeroLastSeen(t *testing.T) {
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {NodeUUID: "uuid-1", NodeName: "Dell-Test", PowerState: strPtr("power on")},
	}
	families := Transform(nodes)
	f := findFamily(families, "ironic_node_last_seen_timestamp_seconds")
	if f != nil && len(f.Samples) > 0 {
		t.Error("zero LastSeen should produce no last_seen sample")
	}
}

func TestTransform_TemperatureSensor(t *testing.T) {
	reading := 26.0
	health := "OK"
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID: "uuid-1",
			NodeName: "Dell-Test",
			Sensors: parser.SensorPayload{
				Temperature: map[string]parser.TemperatureSensor{
					"1@System.Embedded.1": {ReadingCelsius: &reading, PhysicalContext: "SystemBoard", Health: &health},
				},
			},
		},
	}
	families := Transform(nodes)

	fVal := findFamily(families, "ironic_node_temperature_celsius")
	if fVal == nil || len(fVal.Samples) == 0 {
		t.Fatal("expected temperature_celsius sample")
	}
	if fVal.Samples[0].Value != 26 {
		t.Errorf("unexpected celsius value: %v", fVal.Samples[0].Value)
	}
	if findLabel(fVal.Samples[0].Labels, "context") != "SystemBoard" {
		t.Error("expected context=SystemBoard label")
	}

	fHealth := findFamily(families, "ironic_node_temperature_health")
	if fHealth == nil || len(fHealth.Samples) == 0 {
		t.Fatal("expected temperature_health sample")
	}
	if findLabel(fHealth.Samples[0].Labels, "health") != "OK" {
		t.Error("expected health=OK label")
	}
}

func TestTransform_PowerState(t *testing.T) {
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID:       "uuid-1",
			NodeName:       "Dell-Test",
			ConductorHost:  "ironic-conductor.host1",
			HasStateData:   true,
			PowerState:     strPtr("power on"),
			ProvisionState: strPtr("active"),
		},
	}
	families := Transform(nodes)

	f := findFamily(families, "ironic_node_power_state")
	if f == nil || len(f.Samples) == 0 {
		t.Fatal("expected power_state sample")
	}
	if findLabel(f.Samples[0].Labels, "power_state") != "power on" {
		t.Errorf("unexpected power_state label: %v", f.Samples[0].Labels)
	}
	if findLabel(f.Samples[0].Labels, "conductor_host") != "ironic-conductor.host1" {
		t.Error("expected conductor_host label")
	}
}

func TestTransform_MaintenanceAndFault(t *testing.T) {
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID:       "uuid-1",
			NodeName:       "Dell-Test",
			ConductorHost:  "ironic-conductor.host1",
			HasStateData:   true,
			PowerState:     strPtr("power off"),
			ProvisionState: strPtr("error"),
			Maintenance:    true,
			Fault:          strPtr("power failure"),
		},
	}
	families := Transform(nodes)

	fm := findFamily(families, "ironic_node_maintenance")
	if fm == nil || len(fm.Samples) == 0 || fm.Samples[0].Value != 1 {
		t.Error("expected maintenance=1")
	}

	ff := findFamily(families, "ironic_node_fault")
	if ff == nil || len(ff.Samples) == 0 {
		t.Fatal("expected fault sample")
	}
	if findLabel(ff.Samples[0].Labels, "fault") != "power failure" {
		t.Error("expected fault=power failure label")
	}
	if ff.Samples[0].Value != 1 {
		t.Error("expected fault value=1")
	}
}

func TestTransform_SkipsStateMetricsWhenNoStateData(t *testing.T) {
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID: "uuid-1",
			NodeName: "Dell-Test",
			// HasStateData is false — sensor-only node
			Sensors: parser.SensorPayload{
				Temperature: map[string]parser.TemperatureSensor{
					"1@System.Embedded.1": {ReadingCelsius: f64Ptr(26)},
				},
			},
		},
	}
	families := Transform(nodes)

	for _, name := range []string{"ironic_node_maintenance", "ironic_node_fault", "ironic_node_power_state", "ironic_node_provision_state"} {
		f := findFamily(families, name)
		if f != nil && len(f.Samples) > 0 {
			t.Errorf("%s should have no samples when no state data", name)
		}
	}
}

// A maintenance-only event (no power/provision state yet) must still produce
// maintenance and fault metrics once HasStateData is true.
func TestTransform_MaintenanceOnlyEvent(t *testing.T) {
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID:     "uuid-1",
			NodeName:     "Dell-Test",
			HasStateData: true,
			Maintenance:  true,
			// PowerState and ProvisionState are nil — not yet seen
		},
	}
	families := Transform(nodes)

	fm := findFamily(families, "ironic_node_maintenance")
	if fm == nil || len(fm.Samples) == 0 {
		t.Fatal("expected maintenance sample for maintenance-only node")
	}
	if fm.Samples[0].Value != 1 {
		t.Errorf("expected maintenance=1, got %v", fm.Samples[0].Value)
	}
}
