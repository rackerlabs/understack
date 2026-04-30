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

	// TLS — disabled by default, set RABBITMQ_TLS_ENABLED=true to enable amqps://
	TLSEnabled bool
	CAPath     string // RABBITMQ_CA_CERT_PATH   — path to CA certificate
	ServerName string // RABBITMQ_TLS_SERVER_NAME — override SNI when host differs from cert CN/SAN
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
	//reads RABBITMQ_TLS_ENABLED first, then sets defaultPort to 5671 or 5672
	tlsEnabled := getEnvBool("RABBITMQ_TLS_ENABLED", false)
	defaultPort := 5672
	if tlsEnabled {
		defaultPort = 5671
	}

	return &Config{
		RabbitMQ: RabbitMQConfig{
			Host:             getEnv("RABBITMQ_HOST", "localhost"),
			Port:             getEnvInt("RABBITMQ_PORT", defaultPort),
			VHost:            getEnv("RABBITMQ_VHOST", "ironic"),
			Username:         getEnv("RABBITMQ_USERNAME", "ironic"),
			Password:         password,
			Exchange:         getEnv("RABBITMQ_EXCHANGE", "ironic"),
			Queue:            getEnv("RABBITMQ_QUEUE", "ironic-hardware-exporter"),
			RoutingKey:       getEnv("RABBITMQ_ROUTING_KEY", "notifications.info"),
			StatesQueue:      getEnv("RABBITMQ_STATES_QUEUE", "ironic-hardware-exporter-states"),
			StatesRoutingKey: getEnv("RABBITMQ_STATES_ROUTING_KEY", "ironic_versioned_notifications.info"),
			TLSEnabled:       tlsEnabled,
			CAPath:           getEnv("RABBITMQ_CA_CERT_PATH", ""),
			ServerName:       getEnv("RABBITMQ_TLS_SERVER_NAME", ""),
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

func getEnvBool(key string, defaultValue bool) bool {
	if val := os.Getenv(key); val != "" {
		if b, err := strconv.ParseBool(val); err == nil {
			return b
		}
	}
	return defaultValue
}

/* Note: we need 2 queues here .
1st for sensor data (ironic-hardware-exporter)
2nd for state events (ironic-hardware-exporter-states)
both q sit on the same ironic exchange
*/
