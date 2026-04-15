package server

import (
    "fmt"
    "log"
    "net/http"

    "github.com/rackerlabs/understack/go/ironic-hardware-exporter/internal/cache"
)

type Server struct {
    store   *cache.Store
    port    int
    isReady func() bool
}

// when Prometheus scrapes /metrics, the server reads from this to get the latest sensor data.
func New(store *cache.Store, port int, isReady func() bool) *Server {
    return &Server{
        store:   store,
        port:    port,
        isReady: isReady,
    }
}

func (s *Server) Start() error {
    http.HandleFunc("/metrics", s.handleMetrics)
    http.HandleFunc("/health", s.handleHealth)
    http.HandleFunc("/ready", s.handleReady)

    addr := fmt.Sprintf(":%d", s.port)
    log.Printf("HTTP server listening on %s", addr)
    return http.ListenAndServe(addr, nil)
}

func (s *Server) handleMetrics(w http.ResponseWriter, r *http.Request) {
    nodes := s.store.GetAll()
    output := Format(nodes)
    w.Header().Set("Content-Type", "text/plain")
    fmt.Fprint(w, output)
    log.Printf("GET /metrics — served %d nodes", len(nodes))
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(http.StatusOK)
    fmt.Fprint(w, `{"status":"ok"}`)
}

func (s *Server) handleReady(w http.ResponseWriter, r *http.Request) {
    if s.isReady != nil && !s.isReady() {
        w.WriteHeader(http.StatusServiceUnavailable)
        fmt.Fprint(w, `{"status":"not ready"}`)
        return
    }
    nodes := s.store.GetAll()
    fmt.Fprintf(w, `{"status":"ok","nodes":%d}`, len(nodes))
}
