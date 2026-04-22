package parser

import (
	"encoding/json"
	"strings"
	"time"
)

// versioned notifications use a different oslo.message structure from hardware.idrac.metrics
// the actual node data lives inside payload.ironic_object.data

type versionedMessage struct {
	EventType   string           `json:"event_type"`
	PublisherID string           `json:"publisher_id"`
	Payload     versionedPayload `json:"payload"`
	Timestamp   string           `json:"timestamp"`
}

type versionedPayload struct {
	Data nodeStateData `json:"ironic_object.data"`
}

type nodeStateData struct {
	UUID           string  `json:"uuid"`
	Name           string  `json:"name"`
	PowerState     *string `json:"power_state"`
	ProvisionState *string `json:"provision_state"`
	Maintenance    bool    `json:"maintenance"`
	Fault          *string `json:"fault"`
}

// NodeStateMessage is the clean result returned from ParseNodeState.
type NodeStateMessage struct {
	NodeUUID       string
	NodeName       string
	ConductorHost  string
	EventTimestamp time.Time
	PowerState     *string
	ProvisionState *string
	Maintenance    bool
	Fault          *string
}

// nodeStateEventPrefixes are the baremetal.node events .
// we use .end and .success variants so we  capture final state
var nodeStateEventPrefixes = []string{
	"baremetal.node.power_set.end",
	"baremetal.node.provision_set.end",
	"baremetal.node.provision_set.success",
}

func isNodeStateEvent(eventType string) bool {
	for _, prefix := range nodeStateEventPrefixes {
		if strings.EqualFold(eventType, prefix) {
			return true
		}
	}
	return false
}

// ParseNodeState parses versioned Ironic notifications for node power/provision state.
// Returns nil if the event type is not one we care about.
func ParseNodeState(body []byte) (*NodeStateMessage, error) {
	var envelope OsloEnvelope
	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil, err
	}

	var msg versionedMessage
	if err := json.Unmarshal([]byte(envelope.OsloMessage), &msg); err != nil {
		return nil, err
	}

	if !isNodeStateEvent(msg.EventType) {
		return nil, nil
	}

	// timestamp format in versioned notifications: "2026-04-19 00:42:40.397328" (space, not T)
	ts, err := time.Parse("2006-01-02 15:04:05.999999", msg.Timestamp)
	if err != nil {
		ts = time.Now().UTC()
	}

	d := msg.Payload.Data
	return &NodeStateMessage{
		NodeUUID:       d.UUID,
		NodeName:       d.Name,
		ConductorHost:  msg.PublisherID,
		EventTimestamp: ts,
		PowerState:     d.PowerState,
		ProvisionState: d.ProvisionState,
		Maintenance:    d.Maintenance,
		Fault:          d.Fault,
	}, nil
}

/*{
  "oslo.version": "2.0",
  "oslo.message": "{"message_id": "f0b3dfab-846a-47f4-8e2b-4dea9340afaa", "publisher_id": "ironic-conductor.1327175-hp3",
"event_type": "baremetal.node.provision_set.end",
 "priority": "INFO",
"payload": {
"ironic_object.name": "NodeSetProvisionStatePayload",
"ironic_object.namespace": "ironic",
"ironic_object.version": "1.18",
"ironic_object.data": {"uuid": "a8a8548c-fc07-4d9c-a5f2-5f2c6fe7992c",
 "name": "Dell-24GSW04", "power_state": "power on",
"maintenance": false, "maintenance_reason": null,
 "fault": null, "provision_state": "active",
"target_provision_state": null, "last_error": null, "driver": "idrac"}},
 "timestamp": "2026-04-19 00:42:26.870433"}"
}*/
