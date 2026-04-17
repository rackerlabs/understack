package parser

import (
	"encoding/json"
	"log"
	"strings"
	"time"
)

//Messages in rabbitmq are double nested inside oslo.

type OsloEnvelope struct {
	OsloVersion string `json:"oslo.version"`
	OsloMessage string `json:"oslo.message"` // inside this our hardware data is stored
}

//OsloMessage would have this format:
//  "event_type": "hardware.idrac.metrics",
//     "payload": {"node_uuid": 'test',
// 					payload: { {key:value}
//}}
// Now we need to define struct to parse this message
//go needs to define the data type before it marshals the json.

type InnerMessage struct {
	EventType string      `json:"event_type"`
	Payload   NodePayload `json:"payload"`
}

type NodePayload struct {
	NodeUUID  string        `json:"node_uuid"`
	NodeName  string        `json:"node_name"`
	Timestamp string        `json:"timestamp"`
	EventType string        `json:"event_type"`
	Payload   SensorPayload `json:"payload"`
}

// here we ll use map coz we dont know type of data that would come in
// hence map[string]
type SensorPayload struct {
	Fan         map[string]FanSensor         `json:"Fan"`
	Temperature map[string]TemperatureSensor `json:"Temperature"`
	Power       map[string]PowerSensor       `json:"Power"`
	Drive       map[string]DriveSensor       `json:"Drive"`
}

// we need * before type  would give me the actual value at this address
// JSON: "reading_celsius": null  Go sees: nil   (no reading)
// JSON: "reading_celsius": 0   Go sees: &0.0  (reading is actually zero)
type TemperatureSensor struct {
	Identity        string   `json:"identity"`
	ReadingCelsius  *float64 `json:"reading_celsius"` // nil if null
	PhysicalContext string   `json:"physical_context"`
	State           *string  `json:"state"`  // nil if null
	Health          *string  `json:"health"` // nil if null
}

// PowerSensor — one power supply reading.
type PowerSensor struct {
	PowerCapacityWatts   *float64 `json:"power_capacity_watts"`
	LastPowerOutputWatts *float64 `json:"last_power_output_watts"` // nil if null
	SerialNumber         *string  `json:"serial_number"`
	State                *string  `json:"state"`
	Health               *string  `json:"health"`
}

// DriveSensor — one disk drive reading.
type DriveSensor struct {
	Name          *string `json:"name"`
	Model         *string `json:"model"`
	CapacityBytes *int64  `json:"capacity_bytes"`
	State         *string `json:"state"`
	Health        *string `json:"health"`
}

// field shape for fan is unknown
// todo: with real data
type FanSensor struct{}

// collecting all , clean result
type HardwareMessage struct {
	NodeUUID       string
	NodeName       string
	EventTimestamp time.Time
	Sensors        SensorPayload
}

// Parse takes raw bytes from RabbitMQ and returns a clean HardwareMessage.
// The structs above are the skeleton of the message we are going to get.
// []byte is Go's way of saying raw data.
func Parse(body []byte) (*HardwareMessage, error) {

	var envelope OsloEnvelope
	err := json.Unmarshal(body, &envelope)
	if err != nil {
		return nil, err
	}

	var inner InnerMessage
	err = json.Unmarshal([]byte(envelope.OsloMessage), &inner)
	if err != nil {
		return nil, err
	}

	// match any hardware.<driver>.metrics event e.g. hardware.idrac.metrics, hardware.redfish.metrics
	if !strings.HasPrefix(inner.EventType, "hardware.") || !strings.HasSuffix(inner.EventType, ".metrics") {
		return nil, nil // nil means "not a hardware event, skip it"
	}

	// parse the timestamp from the payload e.g. "2026-04-13T15:10:42.960073"
	// if it fails fall back to now so we always have a valid timestamp
	ts, err := time.Parse("2006-01-02T15:04:05.999999", inner.Payload.Timestamp)
	if err != nil {
		log.Printf("warning: could not parse event timestamp %q, falling back to now — Ironic may have changed the timestamp format: %v", inner.Payload.Timestamp, err)
		ts = time.Now().UTC()
	}

	return &HardwareMessage{
		NodeUUID:       inner.Payload.NodeUUID,
		NodeName:       inner.Payload.NodeName,
		EventTimestamp: ts,
		Sensors:        inner.Payload.Payload,
	}, nil

}
