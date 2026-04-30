package main

import (
	"log"

	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/config"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/parser"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/rabbitmq"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/server"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("failed to load config: %v", err)
	}

	store := cache.New()

	// consumer 1: sensor data (hardware.idrac.*.metrics / hardware.redfish.*.metrics)
	sensorConsumer, err := rabbitmq.New(cfg.RabbitMQ)
	if err != nil {
		log.Fatalf("failed to connect sensor consumer to RabbitMQ: %v", err)
	}
	defer sensorConsumer.Close()

	// consumer 2: node state events (baremetal.node.power_set.end, provision_set.end/success)
	// uses a separate private queue bound to the versioned notifications routing key
	statesCfg := cfg.RabbitMQ
	statesCfg.Queue = cfg.RabbitMQ.StatesQueue
	statesCfg.RoutingKey = cfg.RabbitMQ.StatesRoutingKey
	statesConsumer, err := rabbitmq.New(statesCfg)
	if err != nil {
		log.Fatalf("failed to connect states consumer to RabbitMQ: %v", err)
	}
	defer statesConsumer.Close()

	// both consumers must be up for the pod to be considered ready
	bothReady := func() bool {
		return sensorConsumer.IsReady() && statesConsumer.IsReady()
	}
	srv := server.New(store, cfg.Server.Port, bothReady)
	go func() {
		if err := srv.Start(); err != nil {
			log.Fatalf("HTTP server failed: %v", err)
		}
	}()

	// states consumer runs in background goroutine
	go func() {
		log.Println("waiting for node state messages...")
		if err := statesConsumer.Consume(func(body []byte) {
			stateMsg, err := parser.ParseNodeState(body)
			if err != nil {
				log.Printf("failed to parse node state message: %v", err)
				return
			}
			if stateMsg == nil {
				return
			}
			store.UpdateNodeState(stateMsg)
			log.Printf("cached state node=%s power=%v provision=%v",
				stateMsg.NodeName, stateMsg.PowerState, stateMsg.ProvisionState)
		}); err != nil {
			log.Printf("states consumer stopped: %v", err)
		}
	}()

	// sensor consumer blocks main goroutine
	log.Println("waiting for hardware sensor messages...")
	if err := sensorConsumer.Consume(func(body []byte) {
		msg, err := parser.Parse(body)
		if err != nil {
			log.Printf("failed to parse hardware message: %v", err)
			return
		}
		if msg == nil {
			return
		}
		store.Update(msg)
		log.Printf("cached sensors node=%s", msg.NodeName)
	}); err != nil {
		log.Fatalf("sensor consumer stopped: %v", err)
	}
}
