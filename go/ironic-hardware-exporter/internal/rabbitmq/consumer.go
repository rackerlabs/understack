package rabbitmq

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"log"
	"net"
	"net/url"
	"os"
	"strconv"
	"strings"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/config"
)

// Consumer holds the RabbitMQ connection and channel.
// TCP connection to RabbitMQ
// channel lightweight session inside that connection
type Consumer struct {
	conn    *amqp.Connection
	channel *amqp.Channel
	cfg     config.RabbitMQConfig
}

/*Plain string interpolation breaks when passwords containing special characters
%, :, @, or / , or when host is an IPv6 address.
url.UserPassword credential escaping, net.JoinHostPort does IPv6.*/

func buildAMQPURL(cfg config.RabbitMQConfig) string {
	vhost := strings.TrimPrefix(strings.TrimSpace(cfg.VHost), "/")
	if vhost == "" {
		vhost = "/"
	}
	hostPort := net.JoinHostPort(cfg.Host, strconv.Itoa(cfg.Port))
	userInfo := url.UserPassword(cfg.Username, cfg.Password).String()
	scheme := "amqp"
	if cfg.TLSEnabled {
		scheme = "amqps"
	}
	return fmt.Sprintf("%s://%s@%s/%s", scheme, userInfo, hostPort, url.PathEscape(vhost))
}

func buildTLSConfig(cfg config.RabbitMQConfig) (*tls.Config, error) {
	tlsCfg := &tls.Config{}

	if cfg.CAPath != "" {
		caCert, err := os.ReadFile(cfg.CAPath)
		if err != nil {
			return nil, fmt.Errorf("failed to read CA cert %s: %w", cfg.CAPath, err)
		}
		pool := x509.NewCertPool()
		if !pool.AppendCertsFromPEM(caCert) {
			return nil, fmt.Errorf("failed to parse CA cert from %s", cfg.CAPath)
		}
		tlsCfg.RootCAs = pool
	}

	if cfg.ServerName != "" {
		tlsCfg.ServerName = cfg.ServerName
	}

	return tlsCfg, nil
}

func New(cfg config.RabbitMQConfig) (*Consumer, error) {
	rabbitURL := buildAMQPURL(cfg)

	log.Printf("connecting to RabbitMQ at %s:%d vhost=%s tls=%v", cfg.Host, cfg.Port, cfg.VHost, cfg.TLSEnabled)

	var conn *amqp.Connection
	var err error

	if cfg.TLSEnabled {
		tlsCfg, tlsErr := buildTLSConfig(cfg)
		if tlsErr != nil {
			return nil, fmt.Errorf("failed to build TLS config: %w", tlsErr)
		}
		conn, err = amqp.DialConfig(rabbitURL, amqp.Config{TLSClientConfig: tlsCfg})
	} else {
		conn, err = amqp.Dial(rabbitURL)
	}

	if err != nil {
		return nil, fmt.Errorf("failed to connect: %w", err)
	}

	ch, err := conn.Channel()
	if err != nil {
		if closeErr := conn.Close(); closeErr != nil {
			log.Printf("error closing connection after channel failure: %v", closeErr)
		}
		return nil, fmt.Errorf("failed to open channel: %w", err)
	}

	c := &Consumer{conn: conn, channel: ch, cfg: cfg}

	if err := c.setup(); err != nil {
		c.Close()
		return nil, err
	}

	log.Printf("connected to RabbitMQ successfully")
	return c, nil
}

func (c *Consumer) setup() error {
	_, err := c.channel.QueueDeclare(c.cfg.Queue, true, false, false, false, nil)
	if err != nil {
		return fmt.Errorf("failed to declare queue: %w", err)
	}

	err = c.channel.QueueBind(c.cfg.Queue, c.cfg.RoutingKey, c.cfg.Exchange, false, nil)
	if err != nil {
		return fmt.Errorf("failed to bind queue: %w", err)
	}

	log.Printf("queue %s bound to exchange %s", c.cfg.Queue, c.cfg.Exchange)
	return nil
}

func (c *Consumer) Consume(handler func(body []byte)) error {
	msgs, err := c.channel.Consume(c.cfg.Queue, "", false, false, false, false, nil)
	if err != nil {
		return fmt.Errorf("failed to start consuming: %w", err)
	}

	closeCh := make(chan *amqp.Error, 1)
	c.channel.NotifyClose(closeCh)

	log.Printf("waiting for messages from queue: %s", c.cfg.Queue)

	for d := range msgs {
		handler(d.Body)
		if err := d.Ack(false); err != nil {
			log.Printf("failed to ack message: %v", err)
		}
	}
	// silently exit and  returns a generic "connection lost" error
	// now we get like this 'states consumer stopped: channel closed: code=406 reason='
	if amqpErr := <-closeCh; amqpErr != nil {
		return fmt.Errorf("channel closed: code=%d reason=%s", amqpErr.Code, amqpErr.Reason)
	}
	return fmt.Errorf("message channel closed: connection lost")
}

// if either the connection or the channel is closed, /ready returns 503.
func (c *Consumer) IsReady() bool {
	return c != nil && c.conn != nil && !c.conn.IsClosed() &&
		c.channel != nil && !c.channel.IsClosed()
}

func (c *Consumer) Close() {
	if c.channel != nil {
		if err := c.channel.Close(); err != nil {
			log.Printf("error closing channel: %v", err)
		}
	}
	if c.conn != nil {
		if err := c.conn.Close(); err != nil {
			log.Printf("error closing connection: %v", err)
		}
	}
}
