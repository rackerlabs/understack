package controller

import (
	"github.com/prometheus/client_golang/prometheus"
	crmetrics "sigs.k8s.io/controller-runtime/pkg/metrics"
)

// syncItemFailuresGauge tracks the number of individual items that failed to
// sync per resource type on the last reconcile, labelled by Nautobot CR name
// and resource type. A non-zero value means some items were rejected by
// Nautobot (usually a data problem that a human must fix) while the rest still
// synced. The gauge is cleared for a resource when it syncs cleanly so a
// recovery shows up as the value dropping back to 0.
//
// Metric: nautobotop_sync_item_failures{nautobot="<cr-name>",resource="<type>"}
var syncItemFailuresGauge = prometheus.NewGaugeVec(
	prometheus.GaugeOpts{
		Name: "nautobotop_sync_item_failures",
		Help: "Number of individual items that failed to sync per resource type " +
			"on the last reconcile. Non-zero means some items were rejected by " +
			"Nautobot (typically a data problem requiring manual intervention). " +
			"Labelled by Nautobot CR name and resource type.",
	},
	[]string{"nautobot", "resource"},
)

func init() {
	// Register with the controller-runtime metrics registry so the metric is
	// exposed on the standard /metrics endpoint served by the operator manager.
	crmetrics.Registry.MustRegister(syncItemFailuresGauge)
}

// setSyncItemFailuresGauge sets the per-resource failure count gauge for the
// given Nautobot CR. A count of zero clears the gauge entry so recovered
// resource types no longer show (and any alert on them resolves).
func setSyncItemFailuresGauge(crName, resource string, count int) {
	syncItemFailuresGauge.WithLabelValues(crName, resource).Set(float64(count))
}
