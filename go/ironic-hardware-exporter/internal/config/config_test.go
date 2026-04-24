package config

import (
	"testing"
)

// TestLoad_DefaultPortPlain checks that the plain AMQP default port is 5672.
func TestLoad_DefaultPortPlain(t *testing.T) {
	t.Setenv("RABBITMQ_PASSWORD", "secret")
	t.Setenv("RABBITMQ_TLS_ENABLED", "false")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.RabbitMQ.Port != 5672 {
		t.Errorf("expected default port 5672 for plain AMQP, got %d", cfg.RabbitMQ.Port)
	}
}

// TestLoad_DefaultPortTLS checks that the default port switches to 5671 when TLS is enabled.
func TestLoad_DefaultPortTLS(t *testing.T) {
	t.Setenv("RABBITMQ_PASSWORD", "secret")
	t.Setenv("RABBITMQ_TLS_ENABLED", "true")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.RabbitMQ.Port != 5671 {
		t.Errorf("expected default port 5671 when TLS enabled, got %d", cfg.RabbitMQ.Port)
	}
}

// TestLoad_ExplicitPortOverridesTLSDefault checks that RABBITMQ_PORT always wins over the TLS default.
func TestLoad_ExplicitPortOverridesTLSDefault(t *testing.T) {
	t.Setenv("RABBITMQ_PASSWORD", "secret")
	t.Setenv("RABBITMQ_TLS_ENABLED", "true")
	t.Setenv("RABBITMQ_PORT", "5673")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.RabbitMQ.Port != 5673 {
		t.Errorf("expected explicit port 5673, got %d", cfg.RabbitMQ.Port)
	}
}

// TestLoad_ServerName checks that RABBITMQ_TLS_SERVER_NAME is read correctly.
func TestLoad_ServerName(t *testing.T) {
	t.Setenv("RABBITMQ_PASSWORD", "secret")
	t.Setenv("RABBITMQ_TLS_SERVER_NAME", "rabbitmq.internal")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.RabbitMQ.ServerName != "rabbitmq.internal" {
		t.Errorf("expected ServerName=rabbitmq.internal, got %q", cfg.RabbitMQ.ServerName)
	}
}

// TestLoad_MissingPassword checks that Load() returns an error when RABBITMQ_PASSWORD is missing.
func TestLoad_MissingPassword(t *testing.T) {
	t.Setenv("RABBITMQ_PASSWORD", "")

	_, err := Load()
	if err == nil {
		t.Fatal("expected error for missing RABBITMQ_PASSWORD, got nil")
	}
}
