package main

import (
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/config"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/rabbitmq"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/server"
	"log"
)

// WIP
// only for debugging now
func main() {
	// load config from env vars
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("failed to load config: %v", err)
	}

	// create shared cache
	store := cache.New()

	// onnect to RabbitMQ
	consumer, err := rabbitmq.New(cfg.RabbitMQ)
	if err != nil {
		log.Fatalf("failed to connect to RabbitMQ: %v", err)
	}
	defer consumer.Close()

	// start HTTP server in background goroutine
	// /metrics
	srv := server.New(store, cfg.Server.Port, consumer.IsReady)
	go func() {
		if err := srv.Start(); err != nil {
			log.Fatalf("HTTP server failed: %v", err)
		}
	}()

	// consume messages forever (blocks here)
	log.Println("waiting for hardware sensor messages...")
	err = consumer.Consume(func(body []byte) {
		msg, err := parser.Parse(body)
		if err != nil {
			log.Printf("failed to parse message: %v", err)
			return
		}
		if msg == nil {
			return // not a hardware event, skip
		}
		store.Update(msg)
		log.Printf("cached node=%s", msg.NodeName)
	})
	if err != nil {
		log.Fatalf("consumer stopped: %v", err)
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
