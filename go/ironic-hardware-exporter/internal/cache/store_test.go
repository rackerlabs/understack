package cache

import (
	"sync"
	"testing"
	"time"

	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
)

const powerOn = "power on"

func strPtr(s string) *string { return &s }

// Call Update(), then GetAll(), verify NodeName and LastSeen are stored correctly
func TestUpdate_StoresNode(t *testing.T) {
	s := New()
	ts := time.Unix(1776287267, 0)

	s.Update(&parser.HardwareMessage{
		NodeUUID:       "uuid-1",
		NodeName:       "Dell-93GSW04",
		EventTimestamp: ts,
	})

	nodes := s.GetAll()
	n, ok := nodes["uuid-1"]
	if !ok {
		t.Fatal("node not found in cache")
	}
	if n.NodeName != "Dell-93GSW04" {
		t.Errorf("got NodeName=%s, want Dell-93GSW04", n.NodeName)
	}
	if !n.LastSeen.Equal(ts) {
		t.Errorf("got LastSeen=%v, want %v", n.LastSeen, ts)
	}
}

// call Update() twice for the same node with different names.
// Verifies the second one wins for sensor fields.
func TestUpdate_OverwritesSensorData(t *testing.T) {
	s := New()

	s.Update(&parser.HardwareMessage{NodeUUID: "uuid-1", NodeName: "old-name"})
	s.Update(&parser.HardwareMessage{NodeUUID: "uuid-1", NodeName: "new-name"})

	nodes := s.GetAll()
	if nodes["uuid-1"].NodeName != "new-name" {
		t.Errorf("expected new-name, got %s", nodes["uuid-1"].NodeName)
	}
}

// State event arrives first (sets PowerState, ConductorHost), then sensor flood arrives.
// Verifies PowerState and ConductorHost are still there after Update().
func TestUpdate_PreservesStateFields(t *testing.T) {
	s := New()

	// state arrives first
	s.UpdateNodeState(&parser.NodeStateMessage{
		NodeUUID:       "uuid-1",
		NodeName:       "Dell-93GSW04",
		ConductorHost:  "ironic-conductor.host1",
		PowerState:     strPtr(powerOn),
		ProvisionState: strPtr("active"),
		Maintenance:    false,
		Fault:          strPtr("none"),
	})

	// sensor flood arrives , must not wipe state
	s.Update(&parser.HardwareMessage{NodeUUID: "uuid-1", NodeName: "Dell-93GSW04"})

	nodes := s.GetAll()
	n := nodes["uuid-1"]
	if n.PowerState == nil || *n.PowerState != powerOn {
		t.Error("Update() wiped PowerState set by UpdateNodeState()")
	}
	if n.ConductorHost != "ironic-conductor.host1" {
		t.Error("Update() wiped ConductorHost set by UpdateNodeState()")
	}
}

// state event arrives before any sensor data.
// Verifies UpdateNodeState() creates a new entry and sets PowerState, ProvisionState correctly.
func TestUpdateNodeState_CreatesEntryWhenMissing(t *testing.T) {
	s := New()

	s.UpdateNodeState(&parser.NodeStateMessage{
		NodeUUID:       "uuid-1",
		NodeName:       "Dell-24GSW04",
		ConductorHost:  "ironic-conductor.host1",
		PowerState:     strPtr(powerOn),
		ProvisionState: strPtr("active"),
	})

	nodes := s.GetAll()
	n, ok := nodes["uuid-1"]
	if !ok {
		t.Fatal("node not created by UpdateNodeState")
	}
	if *n.PowerState != "power on" {
		t.Errorf("got PowerState=%s, want power on", *n.PowerState)
	}
	if *n.ProvisionState != "active" {
		t.Errorf("got ProvisionState=%s, want active", *n.ProvisionState)
	}
}

// Sensor data arrives first (sets temperature reading), then state event arrives.
// Verifies the temperature reading is still there after UpdateNodeState()
func TestUpdateNodeState_PreservesSensorData(t *testing.T) {
	s := New()
	reading := 26.0

	// first update brings sensor data
	s.Update(&parser.HardwareMessage{
		NodeUUID: "uuid-1",
		NodeName: "Dell-93GSW04",
		Sensors: parser.SensorPayload{
			Temperature: map[string]parser.TemperatureSensor{
				"1@System.Embedded.1": {ReadingCelsius: &reading},
			},
		},
	})

	// then state event arrives , must not wipe sensor data
	s.UpdateNodeState(&parser.NodeStateMessage{
		NodeUUID:   "uuid-1",
		NodeName:   "Dell-93GSW04",
		PowerState: strPtr(powerOn),
	})

	nodes := s.GetAll()
	n := nodes["uuid-1"]
	if n.Sensors.Temperature["1@System.Embedded.1"].ReadingCelsius == nil {
		t.Error("UpdateNodeState wiped sensor data")
	}
	if *n.PowerState != "power on" {
		t.Errorf("got PowerState=%s, want power on", *n.PowerState)
	}
}

// snapshot = GetAll()           // get the map
// snapshot["uuid-1"].NodeName = "mutated"   // change something in it
// snapshot2 = GetAll()          // get the map again
// If GetAll() returns live pointers ,
// changing snapshot also changes what is  inside the store.
// So snapshot2 would show "mutated".
// That is bad because the HTTP handler and RabbitMQ goroutine
// would be touching the same memory.
// when GetAll() returns copies.
// Changing snapshot has no effect on the store. snapshot2 still shows the original value.
// The below test is to test this above scenario
func TestGetAll_ReturnsCopy(t *testing.T) {
	s := New()
	s.Update(&parser.HardwareMessage{NodeUUID: "uuid-1", NodeName: "Dell-93GSW04"})

	snapshot := s.GetAll()
	// mutate the snapshot , should not affect the store
	snapshot["uuid-1"].NodeName = "mutated"

	snapshot2 := s.GetAll()
	if snapshot2["uuid-1"].NodeName == "mutated" {
		t.Error("GetAll returned a live pointer , mutation affected the store")
	}
}

// Fresh store, no nodes.
func TestGetAll_EmptyStore(t *testing.T) {
	s := New()
	nodes := s.GetAll()
	if len(nodes) != 0 {
		t.Errorf("expected empty map, got %d nodes", len(nodes))
	}
}

// spins up 50 goroutines simultaneously writing and reading.
// Tests the RWMutex is working.
// Each iteration starts 2 goroutines simultaneously
// 1 is writer n 2nd is reader
// total 50 writing, 50 reading ;all on the same store, same uuid-1 node.
// If any two goroutines touch the same variable without a lock,
// the test will fails  with a race condition error.
func TestConcurrentUpdateAndGetAll(t *testing.T) {
	// run with -race to catch data races
	s := New()
	var wg sync.WaitGroup

	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			s.Update(&parser.HardwareMessage{
				NodeUUID: "uuid-1",
				NodeName: "Dell-93GSW04",
			})
		}()

		wg.Add(1)
		go func() {
			defer wg.Done()
			_ = s.GetAll()
		}()
	}

	wg.Wait()
}

// UpdateNodeState() and GetAll() racing.
// Verifies the two writers and one reader don't corrupt each other
func TestConcurrentUpdateAndUpdateNodeState(t *testing.T) {
	// run with -race to verify Update and UpdateNodeState don't race on same entry
	s := New()
	s.Update(&parser.HardwareMessage{NodeUUID: "uuid-1", NodeName: "Dell-93GSW04"})

	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			s.UpdateNodeState(&parser.NodeStateMessage{
				NodeUUID:   "uuid-1",
				PowerState: strPtr(powerOn),
			})
		}()

		wg.Add(1)
		go func() {
			defer wg.Done()
			_ = s.GetAll()
		}()
	}

	wg.Wait()
}
