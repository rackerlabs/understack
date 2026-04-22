package server

import (
	"strings"
	"testing"
	"time"

	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
)

func strPtr(s string) *string   { return &s }
func f64Ptr(f float64) *float64 { return &f }

// checks that every metric family has its # HELP and # TYPE header
func TestFormat_ContainsHelpAndTypeHeaders(t *testing.T) {
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID: "uuid-1",
			NodeName: "Dell-Test",
			LastSeen: time.Now(),
		},
	}
	output := Format(nodes)

	for _, header := range []string{
		"# HELP ironic_node_last_seen_timestamp_seconds",
		"# TYPE ironic_node_last_seen_timestamp_seconds gauge",
		"# HELP ironic_node_temperature_celsius",
		"# HELP ironic_node_power_output_watts",
		"# HELP ironic_node_drive_enabled",
		"# HELP ironic_node_power_state",
		"# HELP ironic_node_provision_state",
		"# HELP ironic_node_maintenance",
		"# HELP ironic_node_fault",
	} {
		if !strings.Contains(output, header) {
			t.Errorf("missing header: %s", header)
		}
	}
}

// verifies the Unix timestamp is formatted correctly as an integer.
func TestFormat_LastSeen(t *testing.T) {
	ts := time.Unix(1776287267, 0)
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {NodeUUID: "uuid-1", NodeName: "Dell-Test", LastSeen: ts},
	}
	output := Format(nodes)

	if !strings.Contains(output, `ironic_node_last_seen_timestamp_seconds{node_uuid="uuid-1",node_name="Dell-Test"} 1776287267`) {
		t.Errorf("last_seen metric not found in output:\n%s", output)
	}
}

// checks both the ironic_node_temperature_celsius and ironic_node_temperature_health
// lines appear in the output with correct labels and values.
func TestFormat_TemperatureMetric(t *testing.T) {
	reading := 26.0
	health := "OK"
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID: "uuid-1",
			NodeName: "Dell-Test",
			Sensors: parser.SensorPayload{
				Temperature: map[string]parser.TemperatureSensor{
					"1@System.Embedded.1": {
						ReadingCelsius:  &reading,
						PhysicalContext: "SystemBoard",
						Health:          &health,
					},
				},
			},
		},
	}
	output := Format(nodes)

	if !strings.Contains(output, `ironic_node_temperature_celsius{node_uuid="uuid-1",node_name="Dell-Test",sensor="1@System.Embedded.1",context="SystemBoard"} 26`) {
		t.Errorf("temperature metric not found in output:\n%s", output)
	}
	if !strings.Contains(output, `ironic_node_temperature_health{node_uuid="uuid-1",node_name="Dell-Test",sensor="1@System.Embedded.1",health="OK"} 1`) {
		t.Errorf("temperature health metric not found in output:\n%s", output)
	}
}

// sets PowerState="power on" and ProvisionState="active"
// and checks both state metric lines including the conductor_host label.
func TestFormat_PowerStateMetric(t *testing.T) {
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID:       "uuid-1",
			NodeName:       "Dell-Test",
			ConductorHost:  "ironic-conductor.host1",
			PowerState:     strPtr("power on"),
			ProvisionState: strPtr("active"),
		},
	}
	output := Format(nodes)

	if !strings.Contains(output, `ironic_node_power_state{node_uuid="uuid-1",node_name="Dell-Test",conductor_host="ironic-conductor.host1",power_state="power on"} 1`) {
		t.Errorf("power_state metric not found in output:\n%s", output)
	}
	if !strings.Contains(output, `ironic_node_provision_state{node_uuid="uuid-1",node_name="Dell-Test",conductor_host="ironic-conductor.host1",provision_state="active"} 1`) {
		t.Errorf("provision_state metric not found in output:\n%s", output)
	}
}

// sets Maintenance=true and checks ironic_node_maintenance
func TestFormat_MaintenanceMetric(t *testing.T) {
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID:       "uuid-1",
			NodeName:       "Dell-Test",
			ConductorHost:  "ironic-conductor.host1",
			PowerState:     strPtr("power off"),
			ProvisionState: strPtr("maintenance"),
			Maintenance:    true,
		},
	}
	output := Format(nodes)

	if !strings.Contains(output, `ironic_node_maintenance{node_uuid="uuid-1",node_name="Dell-Test",conductor_host="ironic-conductor.host1"} 1`) {
		t.Errorf("maintenance=1 metric not found in output:\n%s", output)
	}
}

// sets Fault="power failure" and checks ironic_node_fault
func TestFormat_FaultMetric(t *testing.T) {
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID:       "uuid-1",
			NodeName:       "Dell-Test",
			ConductorHost:  "ironic-conductor.host1",
			PowerState:     strPtr("power off"),
			ProvisionState: strPtr("error"),
			Fault:          strPtr("power failure"),
		},
	}
	output := Format(nodes)

	if !strings.Contains(output, `ironic_node_fault{node_uuid="uuid-1",node_name="Dell-Test",conductor_host="ironic-conductor.host1",fault="power failure"} 1`) {
		t.Errorf("fault metric not found in output:\n%s", output)
	}
}

// when node has only sensor data ironic_node_maintenance n ironic_node_fault
// do NOT appear in the output.
func TestFormat_SkipsStateMetricsWhenNoStateData(t *testing.T) {
	// node only has sensor data, no state yet — maintenance/fault should not appear
	nodes := map[string]*cache.NodeEntry{
		"uuid-1": {
			NodeUUID: "uuid-1",
			NodeName: "Dell-Test",
			Sensors: parser.SensorPayload{
				Temperature: map[string]parser.TemperatureSensor{
					"1@System.Embedded.1": {ReadingCelsius: f64Ptr(26)},
				},
			},
		},
	}
	output := Format(nodes)

	if strings.Contains(output, "ironic_node_maintenance{") {
		t.Errorf("maintenance metric should not appear when no state data:\n%s", output)
	}
	if strings.Contains(output, "ironic_node_fault{") {
		t.Errorf("fault metric should not appear when no state data:\n%s", output)
	}
}
