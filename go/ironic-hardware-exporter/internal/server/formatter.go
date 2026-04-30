package server

import (
	"fmt"
	"strings"

	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
)

func Format(nodes map[string]*cache.NodeEntry) string {
	var b strings.Builder
	writeSensorMetrics(&b, nodes)
	writeNodeStateMetrics(&b, nodes)
	return b.String()
}

func writeSensorMetrics(b *strings.Builder, nodes map[string]*cache.NodeEntry) {
	fmt.Fprintf(b, "# HELP ironic_node_last_seen_timestamp_seconds Unix timestamp of the last hardware metrics event received for this node\n")
	fmt.Fprintf(b, "# TYPE ironic_node_last_seen_timestamp_seconds gauge\n")
	for _, n := range nodes {
		fmt.Fprintf(b, "ironic_node_last_seen_timestamp_seconds{node_uuid=%q,node_name=%q} %d\n",
			n.NodeUUID, n.NodeName, n.LastSeen.Unix())
	}

	fmt.Fprintf(b, "# HELP ironic_node_temperature_celsius Temperature reading in Celsius from a node sensor\n")
	fmt.Fprintf(b, "# TYPE ironic_node_temperature_celsius gauge\n")
	for _, n := range nodes {
		for key, t := range n.Sensors.Temperature {
			if t.ReadingCelsius == nil {
				continue
			}
			fmt.Fprintf(b, "ironic_node_temperature_celsius{node_uuid=%q,node_name=%q,sensor=%q,context=%q} %g\n",
				n.NodeUUID, n.NodeName, key, t.PhysicalContext, *t.ReadingCelsius)
		}
	}

	fmt.Fprintf(b, "# HELP ironic_node_power_output_watts Power output in watts from a node power supply\n")
	fmt.Fprintf(b, "# TYPE ironic_node_power_output_watts gauge\n")
	for _, n := range nodes {
		for key, p := range n.Sensors.Power {
			if p.LastPowerOutputWatts == nil {
				continue
			}
			fmt.Fprintf(b, "ironic_node_power_output_watts{node_uuid=%q,node_name=%q,sensor=%q} %g\n",
				n.NodeUUID, n.NodeName, key, *p.LastPowerOutputWatts)
		}
	}

	fmt.Fprintf(b, "# HELP ironic_node_drive_enabled 1 if the drive is in Enabled state, 0 otherwise\n")
	fmt.Fprintf(b, "# TYPE ironic_node_drive_enabled gauge\n")
	for _, n := range nodes {
		for key, d := range n.Sensors.Drive {
			val := 0.0
			if d.State != nil && *d.State == "Enabled" {
				val = 1.0
			}
			fmt.Fprintf(b, "ironic_node_drive_enabled{node_uuid=%q,node_name=%q,sensor=%q} %g\n",
				n.NodeUUID, n.NodeName, key, val)
		}
	}

	// health metrics — emit 1 with health value as label so you can alert on health!="OK"
	fmt.Fprintf(b, "# HELP ironic_node_temperature_health Temperature sensor health reported by iDRAC; value is always 1, health state is in the label\n")
	fmt.Fprintf(b, "# TYPE ironic_node_temperature_health gauge\n")
	for _, n := range nodes {
		for key, t := range n.Sensors.Temperature {
			if t.Health == nil {
				continue
			}
			fmt.Fprintf(b, "ironic_node_temperature_health{node_uuid=%q,node_name=%q,sensor=%q,health=%q} 1\n",
				n.NodeUUID, n.NodeName, key, *t.Health)
		}
	}

	fmt.Fprintf(b, "# HELP ironic_node_power_health Power supply health reported by iDRAC; value is always 1, health state is in the label\n")
	fmt.Fprintf(b, "# TYPE ironic_node_power_health gauge\n")
	for _, n := range nodes {
		for key, p := range n.Sensors.Power {
			if p.Health == nil {
				continue
			}
			fmt.Fprintf(b, "ironic_node_power_health{node_uuid=%q,node_name=%q,sensor=%q,health=%q} 1\n",
				n.NodeUUID, n.NodeName, key, *p.Health)
		}
	}

	fmt.Fprintf(b, "# HELP ironic_node_drive_health Drive health reported by iDRAC; value is always 1, health state is in the label\n")
	fmt.Fprintf(b, "# TYPE ironic_node_drive_health gauge\n")
	for _, n := range nodes {
		for key, d := range n.Sensors.Drive {
			if d.Health == nil {
				continue
			}
			fmt.Fprintf(b, "ironic_node_drive_health{node_uuid=%q,node_name=%q,sensor=%q,health=%q} 1\n",
				n.NodeUUID, n.NodeName, key, *d.Health)
		}
	}
}

func writeNodeStateMetrics(b *strings.Builder, nodes map[string]*cache.NodeEntry) {
	fmt.Fprintf(b, "# HELP ironic_node_power_state Current power state of the node; value is always 1, state is in the label\n")
	fmt.Fprintf(b, "# TYPE ironic_node_power_state gauge\n")
	for _, n := range nodes {
		if n.PowerState == nil {
			continue
		}
		fmt.Fprintf(b, "ironic_node_power_state{node_uuid=%q,node_name=%q,conductor_host=%q,power_state=%q} 1\n",
			n.NodeUUID, n.NodeName, n.ConductorHost, *n.PowerState)
	}

	fmt.Fprintf(b, "# HELP ironic_node_provision_state Current provision state of the node; value is always 1, state is in the label\n")
	fmt.Fprintf(b, "# TYPE ironic_node_provision_state gauge\n")
	for _, n := range nodes {
		if n.ProvisionState == nil {
			continue
		}
		fmt.Fprintf(b, "ironic_node_provision_state{node_uuid=%q,node_name=%q,conductor_host=%q,provision_state=%q} 1\n",
			n.NodeUUID, n.NodeName, n.ConductorHost, *n.ProvisionState)
	}

	fmt.Fprintf(b, "# HELP ironic_node_maintenance 1 if the node is in maintenance mode, 0 otherwise\n")
	fmt.Fprintf(b, "# TYPE ironic_node_maintenance gauge\n")
	for _, n := range nodes {
		if n.PowerState == nil && n.ProvisionState == nil {
			continue
		}
		val := 0.0
		if n.Maintenance {
			val = 1.0
		}
		fmt.Fprintf(b, "ironic_node_maintenance{node_uuid=%q,node_name=%q,conductor_host=%q} %g\n",
			n.NodeUUID, n.NodeName, n.ConductorHost, val)
	}

	fmt.Fprintf(b, "# HELP ironic_node_fault 1 if the node has a fault, 0 otherwise; fault reason is in the label\n")
	fmt.Fprintf(b, "# TYPE ironic_node_fault gauge\n")
	for _, n := range nodes {
		if n.PowerState == nil && n.ProvisionState == nil {
			continue
		}
		fault := "none"
		val := 0.0
		if n.Fault != nil {
			fault = *n.Fault
			val = 1.0
		}
		fmt.Fprintf(b, "ironic_node_fault{node_uuid=%q,node_name=%q,conductor_host=%q,fault=%q} %g\n",
			n.NodeUUID, n.NodeName, n.ConductorHost, fault, val)
	}
}
