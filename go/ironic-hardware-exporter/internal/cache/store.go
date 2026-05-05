package cache

import (
	"sync"
	"time"

	"github.com/maypok86/otter"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
)

// NodeEntry holds everything we know about one physical server.
// Sensor data (temp, power, drive) comes from hardware.idrac.metrics events.
// Node state (power_state, provision_state, maintenance, fault) comes from baremetal.node.* notifications.
// Both are stored together, keyed by node_uuid.
type NodeEntry struct {
	NodeUUID string
	NodeName string
	LastSeen time.Time
	Sensors  parser.SensorPayload

	// node state — updated from versioned notifications (baremetal.node.*)
	// HasStateData is true once any state event has been received for this node.
	HasStateData   bool
	ConductorHost  string
	PowerState     *string
	ProvisionState *string
	Maintenance    bool
	Fault          *string
}

// Store is the in-memory node cache backed by otter.
// mu serialises write sequences (get → copy → modify → set) so two
// concurrent writers cannot overwrite each other's changes.
// GetAll is lock-free: otter's Range sees immutable pointers because
// writers always store a fresh copy, never mutate an entry in place.
type Store struct {
	mu      sync.Mutex
	cache   otter.CacheWithVariableTTL[string, *NodeEntry]
	nodeTTL time.Duration
}

// New creates a Store with the given per-node TTL.
// A node that stops sending events will be evicted after nodeTTL elapses.
func New(nodeTTL time.Duration, maxNodes int) (*Store, error) {
	c, err := otter.MustBuilder[string, *NodeEntry](maxNodes).
		WithVariableTTL().
		Build()
	if err != nil {
		return nil, err
	}
	return &Store{cache: c, nodeTTL: nodeTTL}, nil
}

// Update saves the latest sensor data for a node, called by the sensor consumer goroutine.
// Preserves existing state fields so sensor floods do not overwrite state from versioned notifications.
func (s *Store) Update(msg *parser.HardwareMessage) {
	s.mu.Lock()
	defer s.mu.Unlock()

	var entry NodeEntry
	if existing, ok := s.cache.Get(msg.NodeUUID); ok {
		entry = *existing // copy — never mutate the value otter holds
	} else {
		entry = NodeEntry{NodeUUID: msg.NodeUUID}
	}

	entry.NodeName = msg.NodeName
	entry.LastSeen = msg.EventTimestamp
	entry.Sensors = msg.Sensors
	s.cache.Set(msg.NodeUUID, &entry, s.nodeTTL)
}

// UpdateNodeState saves the latest power/provision/maintenance/fault state for a node.
// Only overwrites PowerState and ProvisionState when the incoming value is non-nil,
// so a maintenance event that omits those fields cannot clear what was already cached.
func (s *Store) UpdateNodeState(msg *parser.NodeStateMessage) {
	s.mu.Lock()
	defer s.mu.Unlock()

	var entry NodeEntry
	if existing, ok := s.cache.Get(msg.NodeUUID); ok {
		entry = *existing
	} else {
		entry = NodeEntry{NodeUUID: msg.NodeUUID, NodeName: msg.NodeName}
	}

	entry.HasStateData = true
	entry.ConductorHost = msg.ConductorHost
	// Only overwrite each field when the incoming value is non-nil.
	// Events that omit a field produce nil for pointer types (*string, *bool),
	// so nil means "absent from this event" — not a valid new value.
	if msg.PowerState != nil {
		entry.PowerState = msg.PowerState
	}
	if msg.ProvisionState != nil {
		entry.ProvisionState = msg.ProvisionState
	}
	if msg.Maintenance != nil {
		entry.Maintenance = *msg.Maintenance
	}
	if msg.Fault != nil {
		entry.Fault = msg.Fault
	}
	s.cache.Set(msg.NodeUUID, &entry, s.nodeTTL)
}

// GetAll returns a snapshot of all nodes for the HTTP handler.
// Lock-free: otter's Range is internally thread-safe and entries stored
// in the cache are never modified after being written.
func (s *Store) GetAll() map[string]*NodeEntry {
	snapshot := make(map[string]*NodeEntry)
	s.cache.Range(func(key string, value *NodeEntry) bool {
		e := *value // struct copy so the caller cannot race with future writes
		snapshot[key] = &e
		return true
	})
	return snapshot
}
