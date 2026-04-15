package cache

import (
    "sync"
    "time"

    "github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
)

// holds everything we know about one server
type NodeEntry struct {
    NodeUUID string
    NodeName string
    LastSeen time.Time
    Sensors  parser.SensorPayload
}

// Store is the in-memory cache, a map protected by a read-write lock
// mu lock , coz 2 gorutines  access this map at same time 
// rabitmq writes, https reads
type Store struct {
    mu    sync.RWMutex
    nodes map[string]*NodeEntry // key = node_uuid value = NodeEntry
}
/* "b6b6dcec-7d48-48c4-89ff-da04b8af40b7" → NodeEntry{
NodeUUID: "b6b6dcec-7d48-48c4-89ff-da04b8af40b7"
                                                NodeName: "Dell-93GSW04"
                                                LastSeen: 2026-04-13 15:10:42
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
                                            }*/
											
// new msg for Dell-93GSW04 would overwrite this entry

// New creates an empty Store
func New() *Store {
    return &Store{
        nodes: make(map[string]*NodeEntry),
    }
}

// Update saves the latest data for a node — called by RabbitMQ goroutine
func (s *Store) Update(msg *parser.HardwareMessage) {
    s.mu.Lock()
    defer s.mu.Unlock()

    s.nodes[msg.NodeUUID] = &NodeEntry{
        NodeUUID: msg.NodeUUID,
        NodeName: msg.NodeName,
        LastSeen: msg.EventTimestamp,
        Sensors:  msg.Sensors,
    }
}

// GetAll returns a copy of all nodes — called by HTTP server when Prometheus scrapes
func (s *Store) GetAll() map[string]*NodeEntry {
    s.mu.RLock()
    defer s.mu.RUnlock()

    snapshot := make(map[string]*NodeEntry, len(s.nodes))
    for k, v := range s.nodes {
        snapshot[k] = v
    }
    return snapshot
}