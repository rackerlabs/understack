package rabbitmq

import (
	"strings"
	"testing"

	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/config"
)

// TestBuildAMQPURL_PlainScheme checks that plain AMQP uses amqp:// scheme.
func TestBuildAMQPURL_PlainScheme(t *testing.T) {
	cfg := config.RabbitMQConfig{
		Host:     "rabbitmq.host",
		Port:     5672,
		VHost:    "ironic",
		Username: "user",
		Password: "pass",
	}
	u := buildAMQPURL(cfg)
	if !strings.HasPrefix(u, "amqp://") {
		t.Errorf("expected amqp:// scheme, got %s", u)
	}
}

// TestBuildAMQPURL_TLSScheme checks that TLS enabled produces an amqps:// URL.
func TestBuildAMQPURL_TLSScheme(t *testing.T) {
	cfg := config.RabbitMQConfig{
		Host:       "rabbitmq.host",
		Port:       5671,
		VHost:      "ironic",
		Username:   "user",
		Password:   "pass",
		TLSEnabled: true,
	}
	u := buildAMQPURL(cfg)
	if !strings.HasPrefix(u, "amqps://") {
		t.Errorf("expected amqps:// scheme, got %s", u)
	}
}

// TestBuildAMQPURL_SpecialCharsInPassword checks that special chars in password are URL-escaped.
func TestBuildAMQPURL_SpecialCharsInPassword(t *testing.T) {
	cfg := config.RabbitMQConfig{
		Host:     "rabbitmq.host",
		Port:     5672,
		VHost:    "ironic",
		Username: "user",
		Password: "p@ss:w/ord%",
	}
	u := buildAMQPURL(cfg)
	if strings.Contains(u, "p@ss:w/ord%") {
		t.Errorf("raw special chars found in URL — password was not escaped: %s", u)
	}
}

// TestBuildTLSConfig_BadCAPath checks that a non-existent CA path returns an error.
func TestBuildTLSConfig_BadCAPath(t *testing.T) {
	cfg := config.RabbitMQConfig{
		CAPath: "/does/not/exist/ca.pem",
	}
	_, err := buildTLSConfig(cfg)
	if err == nil {
		t.Fatal("expected error for missing CA file, got nil")
	}
}

// TestBuildTLSConfig_ServerName checks that ServerName is applied to the TLS config.
func TestBuildTLSConfig_ServerName(t *testing.T) {
	cfg := config.RabbitMQConfig{
		ServerName: "rabbitmq.internal",
	}
	tlsCfg, err := buildTLSConfig(cfg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if tlsCfg.ServerName != "rabbitmq.internal" {
		t.Errorf("expected ServerName=rabbitmq.internal, got %q", tlsCfg.ServerName)
	}
}

// TestBuildTLSConfig_NoPaths checks that an empty config returns a non-nil TLS config with no error.
func TestBuildTLSConfig_NoPaths(t *testing.T) {
	cfg := config.RabbitMQConfig{}
	tlsCfg, err := buildTLSConfig(cfg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if tlsCfg == nil {
		t.Fatal("expected non-nil tls.Config, got nil")
	}
}
