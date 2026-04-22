package parser

import (
	"encoding/json"
	"os"
	"testing"
	"time"
)

// wrapInOslo wraps an inner message struct in an oslo envelope — used to build inline test data.
func wrapInOslo(t *testing.T, inner any) []byte {
	t.Helper()
	innerBytes, err := json.Marshal(inner)
	if err != nil {
		t.Fatalf("could not marshal inner message: %v", err)
	}
	envelope := OsloEnvelope{
		OsloVersion: "2.0",
		OsloMessage: string(innerBytes),
	}
	body, err := json.Marshal(envelope)
	if err != nil {
		t.Fatalf("could not marshal oslo envelope: %v", err)
	}
	return body
}

func readTestData(t *testing.T, filename string) []byte {
	t.Helper()
	data, err := os.ReadFile("testdata/" + filename)
	if err != nil {
		t.Fatalf("could not read testdata/%s: %v", filename, err)
	}
	return data
}

// TestParse_HardwareIDracMetrics checks that a real iDRAC message is parsed correctly.
func TestParse_HardwareIDracMetrics(t *testing.T) {
	body := readTestData(t, "metric.json")

	msg, err := Parse(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg == nil {
		t.Fatal("expected a HardwareMessage, got nil")
	}

	if msg.NodeUUID != "b6b6dcec-7d48-48c4-89ff-da04b8af40b7" {
		t.Errorf("unexpected NodeUUID: %s", msg.NodeUUID)
	}
	if msg.NodeName != "Dell-93GSW04" {
		t.Errorf("unexpected NodeName: %s", msg.NodeName)
	}
}

// TestParse_TimestampFromPayload checks that the timestamp comes from the payload, not time.Now().
func TestParse_TimestampFromPayload(t *testing.T) {
	body := readTestData(t, "metric.json")

	msg, err := Parse(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// payload timestamp is "2026-04-13T15:10:42.960073"
	expected, _ := time.Parse("2006-01-02T15:04:05.999999", "2026-04-13T15:10:42.960073")
	if !msg.EventTimestamp.Equal(expected) {
		t.Errorf("expected timestamp %v, got %v", expected, msg.EventTimestamp)
	}
}

// TestParse_SkipsNonHardwareEvent checks that non-hardware events return nil.
func TestParse_SkipsNonHardwareEvent(t *testing.T) {
	body := readTestData(t, "ironic_metrics_skip.json")

	msg, err := Parse(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg != nil {
		t.Errorf("expected nil for non-hardware event, got message for node %s", msg.NodeName)
	}
}

// TestParse_SensorValues checks that temperature and power readings are parsed correctly.
func TestParse_SensorValues(t *testing.T) {
	body := readTestData(t, "metric.json")

	msg, err := Parse(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// temperature sensor "1@System.Embedded.1" should be 26°C
	temp, ok := msg.Sensors.Temperature["1@System.Embedded.1"]
	if !ok {
		t.Fatal("expected temperature sensor 1@System.Embedded.1 not found")
	}
	if temp.ReadingCelsius == nil || *temp.ReadingCelsius != 26 {
		t.Errorf("expected reading_celsius=26, got %v", temp.ReadingCelsius)
	}
	if temp.Health == nil || *temp.Health != "OK" {
		t.Errorf("expected health=OK, got %v", temp.Health)
	}

	// power sensor "0:Power@System.Embedded.1" should be 9W
	power, ok := msg.Sensors.Power["0:Power@System.Embedded.1"]
	if !ok {
		t.Fatal("expected power sensor 0:Power@System.Embedded.1 not found")
	}
	if power.LastPowerOutputWatts == nil || *power.LastPowerOutputWatts != 9 {
		t.Errorf("expected last_power_output_watts=9, got %v", power.LastPowerOutputWatts)
	}
}

// TestParse_NullReadingsAreNil checks that null JSON values become nil pointers (not zero values).
func TestParse_NullReadingsAreNil(t *testing.T) {
	body := readTestData(t, "metric.json")

	msg, err := Parse(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// sensor "0@System.Embedded.1" has reading_celsius: null
	temp, ok := msg.Sensors.Temperature["0@System.Embedded.1"]
	if !ok {
		t.Fatal("expected temperature sensor 0@System.Embedded.1 not found")
	}
	if temp.ReadingCelsius != nil {
		t.Errorf("expected nil for null reading_celsius, got %v", *temp.ReadingCelsius)
	}
}

// todo: circle back here for parsing
// TestParse_HardwareRedfishMetrics checks that hardware.redfish.metrics is accepted (not just idrac).
// Note: no real redfish nodes exist in the current cluster (all nodes use idrac driver),
// so this uses synthetic test data to verify the broader event type filter works.
// https://docs.openstack.org/ironic/latest/admin/drivers/redfish/metrics.html
// official redfish payload uses lowercase state values like "state": "enabled"
// while iDRAC uses "state": "Enabled" ,
//  so if a real redfish node came in, the drive metric would always show 0 even if the drive is enabled

func TestParse_HardwareRedfishMetrics(t *testing.T) {
	body := readTestData(t, "hardware_redfish_metrics.json")

	msg, err := Parse(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg == nil {
		t.Fatal("expected hardware.redfish.metrics to be accepted, got nil")
	}
	if msg.NodeName != "Dell-93GSW04" {
		t.Errorf("unexpected NodeName: %s", msg.NodeName)
	}
}

// TestParse_InvalidJSON checks that malformed JSON returns an error.
func TestParse_InvalidJSON(t *testing.T) {
	_, err := Parse([]byte(`not valid json`))
	if err == nil {
		t.Fatal("expected an error for invalid JSON, got nil")
	}
}

// TestParse_TimestampFallback checks that a bad timestamp falls back without crashing.
func TestParse_TimestampFallback(t *testing.T) {
	body := wrapInOslo(t, InnerMessage{
		EventType: "hardware.idrac.metrics",
		Payload: NodePayload{
			NodeUUID:  "test-uuid",
			NodeName:  "test-node",
			Timestamp: "not-a-timestamp",
		},
	})

	before := time.Now()
	msg, err := Parse(body)
	after := time.Now()

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msg == nil {
		t.Fatal("expected a message, got nil")
	}
	// timestamp should have fallen back to roughly now
	if msg.EventTimestamp.Before(before) || msg.EventTimestamp.After(after) {
		t.Errorf("fallback timestamp %v is outside expected range [%v, %v]", msg.EventTimestamp, before, after)
	}
}
