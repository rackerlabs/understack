package rabbitmq

import (
    "fmt"
    "log"

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

func New(cfg config.RabbitMQConfig) (*Consumer, error) {
    url := fmt.Sprintf("amqp://%s:%s@%s:%d/%s",
        cfg.Username,
        cfg.Password,
        cfg.Host,
        cfg.Port,
        cfg.VHost,
    )

    log.Printf("connecting to RabbitMQ at %s:%d vhost=%s", cfg.Host, cfg.Port, cfg.VHost)

    conn, err := amqp.Dial(url)
    if err != nil {
        return nil, fmt.Errorf("failed to connect: %w", err)
    }

    ch, err := conn.Channel()
    if err != nil {
        conn.Close()
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

    log.Printf("waiting for messages from queue: %s", c.cfg.Queue)

    for d := range msgs {
        handler(d.Body)
        d.Ack(false)
    }

    return fmt.Errorf("message channel closed connection lost")
}

func (c *Consumer) IsReady() bool {
    return c != nil && c.conn != nil && !c.conn.IsClosed()
}

func (c *Consumer) Close() {
    if c.channel != nil {
        c.channel.Close()
    }
    if c.conn != nil {
        c.conn.Close()
    }
}
