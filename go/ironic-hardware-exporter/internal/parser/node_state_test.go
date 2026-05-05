package parser

import (
	"testing"
	"time"
)

const powerStateOn = "power on"

func boolPtr(b bool) *bool { return &b }

// TestParseNodeState_PowerSetEnd checks that a power_set.end event is parsed correctly.
func TestParseNodeState_PowerSetEnd(t *testing.T) {
	body := readTestData(t, "baremetal_node_power_set.json")

	msg, err := ParseNodeState(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg == nil {
		t.Fatal("expected a NodeStateMessage, got nil")
	}

	if msg.NodeUUID != "a8a8548c-fc07-4d9c-a5f2-5f2c6fe7992c" {
		t.Errorf("unexpected NodeUUID: %s", msg.NodeUUID)
	}
	if msg.NodeName != "Dell-24GSW04" {
		t.Errorf("unexpected NodeName: %s", msg.NodeName)
	}
	if msg.PowerState == nil || *msg.PowerState != "power off" {
		t.Errorf("expected power_state=power off, got %v", msg.PowerState)
	}
	if msg.ProvisionState == nil || *msg.ProvisionState != "deleting" {
		t.Errorf("expected provision_state=deleting, got %v", msg.ProvisionState)
	}
	if msg.Maintenance == nil || *msg.Maintenance {
		t.Errorf("expected maintenance=false, got %v", msg.Maintenance)
	}
	if msg.Fault != nil {
		t.Errorf("expected fault=nil, got %v", *msg.Fault)
	}
}

// TestParseNodeState_ProvisionSetEnd checks that a provision_set.end event is parsed correctly.
func TestParseNodeState_ProvisionSetEnd(t *testing.T) {
	body := readTestData(t, "baremetal_node_provision_set.json")

	msg, err := ParseNodeState(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg == nil {
		t.Fatal("expected a NodeStateMessage, got nil")
	}

	if msg.ProvisionState == nil || *msg.ProvisionState != "active" {
		t.Errorf("expected provision_state=active, got %v", msg.ProvisionState)
	}
	if msg.PowerState == nil || *msg.PowerState != powerStateOn {
		t.Errorf("expected power_state=power on, got %v", msg.PowerState)
	}
}

// TestParseNodeState_SkipsUnrelatedEvent checks that events we don't care about return nil.
func TestParseNodeState_SkipsUnrelatedEvent(t *testing.T) {
	body := readTestData(t, "ironic_metrics_skip.json")

	msg, err := ParseNodeState(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg != nil {
		t.Errorf("expected nil for unrelated event, got message for node %s", msg.NodeName)
	}
}

// TestParseNodeState_SkipsStartEvents checks that .start events are ignored, we only want final state.
func TestParseNodeState_SkipsStartEvents(t *testing.T) {
	body := wrapInOslo(t, versionedMessage{
		EventType: "baremetal.node.power_set.start",
		Payload: versionedPayload{
			Data: nodeStateData{UUID: "test-uuid", Name: "test-node"},
		},
		Timestamp: "2026-04-19 00:42:40.000000",
	})

	msg, err := ParseNodeState(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg != nil {
		t.Errorf("expected nil for .start event, got message for node %s", msg.NodeName)
	}
}

// TestParseNodeState_Timestamp checks the timestamp is parsed from the payload.
// versioned notifications use space separator: "2026-04-19 00:42:40.397328" (not T)
// we need this because sensor data uses T separator
func TestParseNodeState_Timestamp(t *testing.T) {
	body := readTestData(t, "baremetal_node_power_set.json")

	msg, err := ParseNodeState(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	expected, _ := time.Parse("2006-01-02 15:04:05.999999", "2026-04-19 00:42:40.397328")
	if !msg.EventTimestamp.Equal(expected) {
		t.Errorf("expected timestamp %v, got %v", expected, msg.EventTimestamp)
	}
}

// TestParseNodeState_MaintenanceSet checks that maintenance.set events are accepted.
// These events can change the maintenance field without any power/provision state change.
func TestParseNodeState_MaintenanceSet(t *testing.T) {
	body := wrapInOslo(t, versionedMessage{
		EventType: "baremetal.node.maintenance.set",
		Payload: versionedPayload{
			Data: nodeStateData{UUID: "test-uuid", Name: "test-node", Maintenance: boolPtr(true)},
		},
		Timestamp: "2026-04-19 00:42:40.000000",
	})

	msg, err := ParseNodeState(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg == nil {
		t.Fatal("expected a NodeStateMessage for maintenance.set, got nil")
	}
	if msg.Maintenance == nil || !*msg.Maintenance {
		t.Errorf("expected maintenance=true, got false")
	}
}

// TestParseNodeState_PowerStateCorrected checks that power_state_corrected events are accepted.
func TestParseNodeState_PowerStateCorrected(t *testing.T) {
	state := powerStateOn
	body := wrapInOslo(t, versionedMessage{
		EventType: "baremetal.node.power_state_corrected",
		Payload: versionedPayload{
			Data: nodeStateData{UUID: "test-uuid", Name: "test-node", PowerState: &state},
		},
		Timestamp: "2026-04-19 00:42:40.000000",
	})

	msg, err := ParseNodeState(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg == nil {
		t.Fatal("expected a NodeStateMessage for power_state_corrected, got nil")
	}
	if msg.PowerState == nil || *msg.PowerState != powerStateOn {
		t.Errorf("expected power_state=power on, got %v", msg.PowerState)
	}
}

// TestParseNodeState_UpdateEnd checks that update.end events are accepted.
// Nautobot sync already treats this as a node-state event source.
func TestParseNodeState_UpdateEnd(t *testing.T) {
	provision := "manageable"
	fault := "clean failed"
	body := wrapInOslo(t, versionedMessage{
		EventType: "baremetal.node.update.end",
		Payload: versionedPayload{
			Data: nodeStateData{
				UUID:           "test-uuid",
				Name:           "test-node",
				ProvisionState: &provision,
				Maintenance:    boolPtr(true),
				Fault:          &fault,
			},
		},
		Timestamp: "2026-04-19 00:42:40.000000",
	})

	msg, err := ParseNodeState(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg == nil {
		t.Fatal("expected a NodeStateMessage for update.end, got nil")
	}
	if msg.ProvisionState == nil || *msg.ProvisionState != "manageable" {
		t.Errorf("expected provision_state=manageable, got %v", msg.ProvisionState)
	}
	if msg.Maintenance == nil || !*msg.Maintenance {
		t.Errorf("expected maintenance=true, got false")
	}
	if msg.Fault == nil || *msg.Fault != "clean failed" {
		t.Errorf("expected fault=clean failed, got %v", msg.Fault)
	}
}

// TestParseNodeState_InvalidJSON checks that malformed JSON returns an error.
func TestParseNodeState_InvalidJSON(t *testing.T) {
	_, err := ParseNodeState([]byte(`not valid json`))
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}
