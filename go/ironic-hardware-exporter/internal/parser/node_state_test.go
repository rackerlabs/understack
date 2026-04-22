package parser

import (
	"testing"
	"time"
)

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
	if msg.Maintenance != false {
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
	if msg.PowerState == nil || *msg.PowerState != "power on" {
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

// TestParseNodeState_InvalidJSON checks that malformed JSON returns an error.
func TestParseNodeState_InvalidJSON(t *testing.T) {
	_, err := ParseNodeState([]byte(`not valid json`))
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}
