package main

import (
    "fmt"
    "os"
    "github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
    "github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
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
}

