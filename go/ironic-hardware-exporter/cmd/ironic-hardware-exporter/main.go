package main

import (
    "fmt"
    "os"
    "github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
    "github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
    "log"
    "github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/server"
)
//WIP
//only for debugging now
func main() {
    body, _ := os.ReadFile("internal/parser/testdata/hardware_idrac_metrics.json")
    msg, err := parser.Parse(body)
    if err != nil {
        fmt.Println("ERROR:", err)
        return
    }
    if msg == nil {
        fmt.Println("skipped — not a hardware event")
        return
    }
    // fmt.Println("node:", msg.NodeName)
    // fmt.Println("uuid:", msg.NodeUUID)
    // fmt.Println("time:", msg.EventTimestamp)

    store := cache.New()
    store.Update(msg)
    nodes := store.GetAll()
    fmt.Println("nodes in cache:", len(nodes))
    for _, n := range nodes {
        fmt.Println("node:", n.NodeName, "last seen:", n.LastSeen)
        for sensorKey, temp := range n.Sensors.Temperature {
            if temp.ReadingCelsius != nil {
                fmt.Println("  temp sensor:", sensorKey, "=", *temp.ReadingCelsius, "°C")
            }
        }
        for sensorKey, psu := range n.Sensors.Power {
            if psu.LastPowerOutputWatts != nil {
                fmt.Println("  power sensor:", sensorKey, "=", *psu.LastPowerOutputWatts, "W")
            }
        }
    }
    // start HTTP server to test formatter output
    // http://metrics
    srv := server.New(store, 9608, func() bool { return true })
    if err := srv.Start(); err != nil {
        log.Fatal(err)
    }
}

// 
// nodes in cache: 1
// node: Dell-93GSW04 last seen: 2026-04-15 11:04:47.765968 +0000 UTC
//   temp sensor: 1@System.Embedded.1 = 26 °C
//   power sensor: 0:Power@System.Embedded.1 = 9 W


// ironic_node_last_seen_timestamp_seconds{node_uuid="b6b6dcec-7d48-48c4-89ff-da04b8af40b7",node_name="Dell-93GSW04"} 1776258019
// ironic_node_temperature_celsius{node_uuid="b6b6dcec-7d48-48c4-89ff-da04b8af40b7",node_name="Dell-93GSW04",sensor="1@System.Embedded.1",context="SystemBoard"} 26
// ironic_node_power_output_watts{node_uuid="b6b6dcec-7d48-48c4-89ff-da04b8af40b7",node_name="Dell-93GSW04",sensor="0:Power@System.Embedded.1"} 9
// ironic_node_drive_enabled{node_uuid="b6b6dcec-7d48-48c4-89ff-da04b8af40b7",node_name="Dell-93GSW04",sensor="Solid State Disk 0:1:0:RAID.SL.1-1@System.Embedded.1"} 1
