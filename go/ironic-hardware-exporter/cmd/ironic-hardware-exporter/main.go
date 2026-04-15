package main

import (
    "fmt"
    "os"
    "github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
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
    fmt.Println("node:", msg.NodeName)
    fmt.Println("uuid:", msg.NodeUUID)
    fmt.Println("time:", msg.EventTimestamp)
}

