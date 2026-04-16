package server

import (
	"fmt"
	"strings"

	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
)

func Format(nodes map[string]*cache.NodeEntry) string {
	var b strings.Builder

	// todo: need to know about # HELP and # TYPE headers, saw it in existing log

	for _, n := range nodes {
		fmt.Fprintf(&b, "ironic_node_last_seen_timestamp_seconds{node_uuid=%q,node_name=%q} %d\n",
			n.NodeUUID, n.NodeName, n.LastSeen.Unix())
	}

	for _, n := range nodes {
		for key, t := range n.Sensors.Temperature {
			if t.ReadingCelsius == nil {
				continue
			}
			fmt.Fprintf(&b, "ironic_node_temperature_celsius{node_uuid=%q,node_name=%q,sensor=%q,context=%q} %g\n",
				n.NodeUUID, n.NodeName, key, t.PhysicalContext, *t.ReadingCelsius)
		}
	}

	for _, n := range nodes {
		for key, p := range n.Sensors.Power {
			if p.LastPowerOutputWatts == nil {
				continue
			}
			fmt.Fprintf(&b, "ironic_node_power_output_watts{node_uuid=%q,node_name=%q,sensor=%q} %g\n",
				n.NodeUUID, n.NodeName, key, *p.LastPowerOutputWatts)
		}
	}

	for _, n := range nodes {
		for key, d := range n.Sensors.Drive {
			val := 0.0
			if d.State != nil && *d.State == "Enabled" {
				val = 1.0
			}
			fmt.Fprintf(&b, "ironic_node_drive_enabled{node_uuid=%q,node_name=%q,sensor=%q} %g\n",
				n.NodeUUID, n.NodeName, key, val)
		}
	}

	// health metrics — emit 1 with health value as label so you can alert on health!="OK"
	for _, n := range nodes {
		for key, t := range n.Sensors.Temperature {
			if t.Health == nil {
				continue
			}
			fmt.Fprintf(&b, "ironic_node_temperature_health{node_uuid=%q,node_name=%q,sensor=%q,health=%q} 1\n",
				n.NodeUUID, n.NodeName, key, *t.Health)
		}
	}

	for _, n := range nodes {
		for key, p := range n.Sensors.Power {
			if p.Health == nil {
				continue
			}
			fmt.Fprintf(&b, "ironic_node_power_health{node_uuid=%q,node_name=%q,sensor=%q,health=%q} 1\n",
				n.NodeUUID, n.NodeName, key, *p.Health)
		}
	}

	for _, n := range nodes {
		for key, d := range n.Sensors.Drive {
			if d.Health == nil {
				continue
			}
			fmt.Fprintf(&b, "ironic_node_drive_health{node_uuid=%q,node_name=%q,sensor=%q,health=%q} 1\n",
				n.NodeUUID, n.NodeName, key, *d.Health)
		}
	}

	return b.String()
}
