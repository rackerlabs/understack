package main

import (
	"log"

	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/config"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/rabbitmq"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/server"
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
