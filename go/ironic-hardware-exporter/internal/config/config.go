package config

import(
"fmt"
"os"
)

//strut to hold the config
//funcn to read env vars

type RabbitMQConfig struct {
	Host string
	Port int
	VHost string
	Username string
	Password string
	Exchange string
	Queue string
	RoutingKey string
}

type ServerConfig struct {
	Port int
}

type Config struct {
	RabbitMQ RabbitMQConfig
	Server ServerConfig
}

func Load() (*Config, error){
	password := os.Getenv("RABBITMQ_PASSWORD")
	if password == "" {
		return nil, fmt.Errorf("RABBITMQ_PASSWORD is required")
	}
	return &Config{
		    RabbitMQ: RabbitMQConfig{
            Host:       getEnv("RABBITMQ_HOST", "localhost"),
            Port:       5672,
            VHost:      getEnv("RABBITMQ_VHOST", "ironic"),
            Username:   getEnv("RABBITMQ_USERNAME", "ironic"),
            Password:   password,
            Exchange:   getEnv("RABBITMQ_EXCHANGE", "ironic"),
            Queue:      getEnv("RABBITMQ_QUEUE", "ironic-hardware-exporter"),
            RoutingKey: getEnv("RABBITMQ_ROUTING_KEY", "notifications.info"),
        },
        Server: ServerConfig{
            Port: 9608,
        },
    }, nil
}

func getEnv(key, defaultValue string) string {
    if val := os.Getenv(key); val != "" {
        return val
    }
    return defaultValue
}
