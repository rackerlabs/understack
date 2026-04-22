package cache

import (
	"sync"
	"time"

	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
)

// holds everything we know about one server
// sensor data (temp, power, drive) comes from hardware.idrac.metrics events
// node state (power_state, provision_state, maintenance, fault) comes from baremetal.node.* versioned notify
// both are stored in a single NodeEntry, connected by node_uuid
type NodeEntry struct {
	NodeUUID string
	NodeName string
	LastSeen time.Time
	Sensors  parser.SensorPayload

	// node state — updated from versioned notifications (baremetal.node.*)
	ConductorHost  string
	PowerState     *string
	ProvisionState *string
	Maintenance    bool
	Fault          *string
}

// Store is the in-memory cache, a map protected by a read-write lock
// mu lock , because 2 goroutines access this map at same time
// rabbitmq writes, http reads
type Store struct {
	mu    sync.RWMutex
	nodes map[string]*NodeEntry // key = node_uuid value = NodeEntry
}

/* "b6b6dcec-7d48-48c4-89ff-da04b8af40b7" → NodeEntry{
NodeUUID: "b6b6dcec-7d48-48c4-89ff-da04b8af40b7"
                                                NodeName: "Dell-93GSW04"
                                                LastSeen: 2026-04-13 15:10:42 (from sensor event)
                                                Sensors: {
                                                    Temperature: {
                                                        "1@System.Embedded.1": {reading: 26°C}
                                                    }
                                                    Power: {
                                                        "0:Power@System.Embedded.1": {watts: 9}
                                                        "1:Power@System.Embedded.1": {watts: 0}
                                                    }
                                                    Drive: {
                                                        "Solid State Disk 0:1:0:...": {state: Enabled}
                                                        "Solid State Disk 0:1:1:...": {state: Enabled}
                                                    }
                                                }
											ConductorHost:  "ironic-conductor.1327175-hp3" (from state event)
											PowerState:     "power on"
											ProvisionState: "active"
											Maintenance:    false
											Fault:          nil
                                            }*/

// new msg for Dell-93GSW04 would overwrite this entry

// New creates an empty Store
func New() *Store {
	return &Store{
		nodes: make(map[string]*NodeEntry),
	}
}

// Update saves the latest sensor data for a node  called by RabbitMQ goroutine.
// preserves existing state fields (power_state, provision_state, nall)
// so sensor floods do not overwrite state learned from versioned notifications.
func (s *Store) Update(msg *parser.HardwareMessage) {
	s.mu.Lock()
	defer s.mu.Unlock()

	entry, exists := s.nodes[msg.NodeUUID]
	if !exists {
		entry = &NodeEntry{NodeUUID: msg.NodeUUID}
		s.nodes[msg.NodeUUID] = entry
	}

	entry.NodeName = msg.NodeName
	entry.LastSeen = msg.EventTimestamp
	entry.Sensors = msg.Sensors
}

// UpdateNodeState saves the latest power/provision state for a node.
// uses the same NodeEntry as Update so both sensor and state data live together.
// if node doesn't exist yet in cache we create a minimal entry.
func (s *Store) UpdateNodeState(msg *parser.NodeStateMessage) {
	s.mu.Lock()
	defer s.mu.Unlock()

	entry, exists := s.nodes[msg.NodeUUID]
	if !exists {
		entry = &NodeEntry{
			NodeUUID: msg.NodeUUID,
			NodeName: msg.NodeName,
		}
		s.nodes[msg.NodeUUID] = entry
	}

	entry.ConductorHost = msg.ConductorHost
	entry.PowerState = msg.PowerState
	entry.ProvisionState = msg.ProvisionState
	entry.Maintenance = msg.Maintenance
	entry.Fault = msg.Fault
}

// GetAll returns a snapshot of all nodes called by HTTP server when Prometheus scrapes.
// Each entry is a struct copy so the HTTP handler and RabbitMQ goroutine
// cannot race on the same NodeEntry fields.
func (s *Store) GetAll() map[string]*NodeEntry {
	s.mu.RLock()
	defer s.mu.RUnlock()

	snapshot := make(map[string]*NodeEntry, len(s.nodes))
	for k, v := range s.nodes {
		entry := *v
		snapshot[k] = &entry
	}
	return snapshot
}

/* NodeEntry holds everything we know about one physical node.
sensor data n node state  both are stored in a NodeEntry, with common  node_uuid
so when prometheus scrapes /metrics, we have the full picture of a node in one place
sensor data and state data arrive independently from two separate queues
Update() writes sensor fields, UpdateNodeState() writes state fields
neither overwrites the other */
