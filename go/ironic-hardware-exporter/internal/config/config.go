package config

import (
	"fmt"
	"os"
	"strconv"
)

//struct to hold the config
//function to read env vars

type RabbitMQConfig struct {
	Host       string
	Port       int
	VHost      string
	Username   string
	Password   string
	Exchange   string
	Queue      string
	RoutingKey string

	// 2nd q for versioned notifications (node power/provision state events)
	StatesQueue      string
	StatesRoutingKey string
}

type ServerConfig struct {
	Port int
}

type Config struct {
	RabbitMQ RabbitMQConfig
	Server   ServerConfig
}

func Load() (*Config, error) {
	password := os.Getenv("RABBITMQ_PASSWORD")
	if password == "" {
		return nil, fmt.Errorf("RABBITMQ_PASSWORD is required")
	}
	return &Config{
		RabbitMQ: RabbitMQConfig{
			Host:             getEnv("RABBITMQ_HOST", "localhost"),
			Port:             getEnvInt("RABBITMQ_PORT", 5672),
			VHost:            getEnv("RABBITMQ_VHOST", "ironic"),
			Username:         getEnv("RABBITMQ_USERNAME", "ironic"),
			Password:         password,
			Exchange:         getEnv("RABBITMQ_EXCHANGE", "ironic"),
			Queue:            getEnv("RABBITMQ_QUEUE", "ironic-hardware-exporter"),
			RoutingKey:       getEnv("RABBITMQ_ROUTING_KEY", "notifications.info"),
			StatesQueue:      getEnv("RABBITMQ_STATES_QUEUE", "ironic-hardware-exporter-states"),
			StatesRoutingKey: getEnv("RABBITMQ_STATES_ROUTING_KEY", "ironic_versioned_notifications.info"),
		},
		Server: ServerConfig{
			Port: getEnvInt("SERVER_PORT", 9608),
		},
	}, nil
}

func getEnv(key, defaultValue string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultValue
}

func getEnvInt(key string, defaultValue int) int {
	if val := os.Getenv(key); val != "" {
		if n, err := strconv.Atoi(val); err == nil {
			return n
		}
	}
	return defaultValue
}

/* Note: we need 2 queues here .
1st for sensor data (ironic-hardware-exporter)
2nd for state events (ironic-hardware-exporter-states)
both q  sit on the same ironic exchange
*/
