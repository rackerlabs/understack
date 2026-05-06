package metrics

import (
	"fmt"
	"strings"
)

// Render writes a slice of MetricFamily values as Prometheus text format.
func Render(families []MetricFamily) string {
	var b strings.Builder
	for _, f := range families {
		fmt.Fprintf(&b, "# HELP %s %s\n", f.Name, f.Help)
		fmt.Fprintf(&b, "# TYPE %s gauge\n", f.Name)
		for _, s := range f.Samples {
			fmt.Fprintf(&b, "%s{%s} %g\n", f.Name, renderLabels(s.Labels), s.Value)
		}
	}
	return b.String()
}

func renderLabels(labels []Label) string {
	parts := make([]string, len(labels))
	for i, l := range labels {
		parts[i] = fmt.Sprintf("%s=%q", l.Name, l.Value)
	}
	return strings.Join(parts, ",")
}
