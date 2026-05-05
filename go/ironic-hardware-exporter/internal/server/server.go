package server

import (
	"fmt"
	"log"
	"net/http"

	"github.com/labstack/echo/v4"
	"github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
)

const contentTypePrometheus = "text/plain; version=0.0.4; charset=utf-8"

type Server struct {
	store   *cache.Store
	port    int
	isReady func() bool
}

func New(store *cache.Store, port int, isReady func() bool) *Server {
	return &Server{store: store, port: port, isReady: isReady}
}

func (s *Server) Start() error {
	e := echo.New()
	e.HideBanner = true

	e.GET("/metrics", s.handleMetrics)
	e.GET("/health", s.handleHealth)
	e.GET("/ready", s.handleReady)

	addr := fmt.Sprintf(":%d", s.port)
	log.Printf("HTTP server listening on %s", addr)
	return e.Start(addr)
}

func (s *Server) handleMetrics(c echo.Context) error {
	nodes := s.store.GetAll()
	families := Transform(nodes)
	output := Render(families)
	log.Printf("GET /metrics — served %d nodes", len(nodes))
	return c.Blob(http.StatusOK, contentTypePrometheus, []byte(output))
}

func (s *Server) handleHealth(c echo.Context) error {
	return c.JSON(http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleReady(c echo.Context) error {
	if s.isReady != nil && !s.isReady() {
		return c.JSON(http.StatusServiceUnavailable, map[string]string{"status": "not ready"})
	}
	nodes := s.store.GetAll()
	return c.JSON(http.StatusOK, map[string]any{"status": "ok", "nodes": len(nodes)})
}
