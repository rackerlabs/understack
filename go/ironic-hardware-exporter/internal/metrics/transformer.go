package metrics

import (
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
)

// MetricFamily is a single Prometheus gauge family with all its samples.
type MetricFamily struct {
	Name    string
	Help    string
	Samples []Sample
}

// Sample is one label-set/value pair within a MetricFamily.
type Sample struct {
	Labels []Label
	Value  float64
}

// Label is a single Prometheus label name/value pair.
type Label struct {
	Name  string
	Value string
}

// Transform converts a snapshot of NodeEntry records into a slice of MetricFamily
// values ready to be rendered as Prometheus text.
func Transform(nodes map[string]*cache.NodeEntry) []MetricFamily {
	sensor := sensorFamilies(nodes)
	state := stateFamilies(nodes)
	families := make([]MetricFamily, 0, len(sensor)+len(state))
	families = append(families, sensor...)
	families = append(families, state...)
	return families
}

func sensorFamilies(nodes map[string]*cache.NodeEntry) []MetricFamily {
	lastSeen := MetricFamily{Name: "ironic_node_last_seen_timestamp_seconds", Help: "Unix timestamp of the last hardware metrics event received for this node"}
	tempVal := MetricFamily{Name: "ironic_node_temperature_celsius", Help: "Temperature reading in Celsius from a node sensor"}
	tempHealth := MetricFamily{Name: "ironic_node_temperature_health", Help: "Temperature sensor health; value is always 1, health state is in the label"}
	powerVal := MetricFamily{Name: "ironic_node_power_output_watts", Help: "Power output in watts from a node power supply"}
	powerHealth := MetricFamily{Name: "ironic_node_power_health", Help: "Power supply health; value is always 1, health state is in the label"}
	driveEnabled := MetricFamily{Name: "ironic_node_drive_enabled", Help: "1 if the drive is in Enabled state, 0 otherwise"}
	driveHealth := MetricFamily{Name: "ironic_node_drive_health", Help: "Drive health; value is always 1, health state is in the label"}

	for _, n := range nodes {
		if !n.LastSeen.IsZero() {
			lastSeen.Samples = append(lastSeen.Samples, Sample{
				Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}},
				Value:  float64(n.LastSeen.Unix()),
			})
		}

		for key, t := range n.Sensors.Temperature {
			if t.ReadingCelsius != nil {
				tempVal.Samples = append(tempVal.Samples, Sample{
					Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "sensor", Value: key}, {Name: "context", Value: t.PhysicalContext}},
					Value:  *t.ReadingCelsius,
				})
			}
			if t.Health != nil {
				tempHealth.Samples = append(tempHealth.Samples, Sample{
					Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "sensor", Value: key}, {Name: "health", Value: *t.Health}},
					Value:  1,
				})
			}
		}

		for key, p := range n.Sensors.Power {
			if p.LastPowerOutputWatts != nil {
				powerVal.Samples = append(powerVal.Samples, Sample{
					Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "sensor", Value: key}},
					Value:  *p.LastPowerOutputWatts,
				})
			}
			if p.Health != nil {
				powerHealth.Samples = append(powerHealth.Samples, Sample{
					Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "sensor", Value: key}, {Name: "health", Value: *p.Health}},
					Value:  1,
				})
			}
		}

		for key, d := range n.Sensors.Drive {
			val := 0.0
			if d.State != nil && *d.State == "Enabled" {
				val = 1.0
			}
			driveEnabled.Samples = append(driveEnabled.Samples, Sample{
				Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "sensor", Value: key}},
				Value:  val,
			})
			if d.Health != nil {
				driveHealth.Samples = append(driveHealth.Samples, Sample{
					Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "sensor", Value: key}, {Name: "health", Value: *d.Health}},
					Value:  1,
				})
			}
		}
	}

	return []MetricFamily{lastSeen, tempVal, tempHealth, powerVal, powerHealth, driveEnabled, driveHealth}
}

func stateFamilies(nodes map[string]*cache.NodeEntry) []MetricFamily {
	powerState := MetricFamily{Name: "ironic_node_power_state", Help: "Current power state of the node; value is always 1, state is in the label"}
	provisionState := MetricFamily{Name: "ironic_node_provision_state", Help: "Current provision state of the node; value is always 1, state is in the label"}
	maintenance := MetricFamily{Name: "ironic_node_maintenance", Help: "1 if the node is in maintenance mode, 0 otherwise"}
	fault := MetricFamily{Name: "ironic_node_fault", Help: "1 if the node has a fault, 0 otherwise; fault reason is in the label"}

	for _, n := range nodes {
		if !n.HasStateData {
			continue
		}

		if n.PowerState != nil {
			powerState.Samples = append(powerState.Samples, Sample{
				Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "conductor_host", Value: n.ConductorHost}, {Name: "power_state", Value: *n.PowerState}},
				Value:  1,
			})
		}

		if n.ProvisionState != nil {
			provisionState.Samples = append(provisionState.Samples, Sample{
				Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "conductor_host", Value: n.ConductorHost}, {Name: "provision_state", Value: *n.ProvisionState}},
				Value:  1,
			})
		}

		mVal := 0.0
		if n.Maintenance {
			mVal = 1.0
		}
		maintenance.Samples = append(maintenance.Samples, Sample{
			Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "conductor_host", Value: n.ConductorHost}},
			Value:  mVal,
		})

		faultStr := "none"
		faultVal := 0.0
		if n.Fault != nil {
			faultStr = *n.Fault
			faultVal = 1.0
		}
		fault.Samples = append(fault.Samples, Sample{
			Labels: []Label{{Name: "node_uuid", Value: n.NodeUUID}, {Name: "node_name", Value: n.NodeName}, {Name: "conductor_host", Value: n.ConductorHost}, {Name: "fault", Value: faultStr}},
			Value:  faultVal,
		})
	}

	return []MetricFamily{powerState, provisionState, maintenance, fault}
}
