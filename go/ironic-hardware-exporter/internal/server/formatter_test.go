package server

import (
	"strings"
	"testing"
)

func strPtr(s string) *string   { return &s }
func f64Ptr(f float64) *float64 { return &f }

func TestRender_HelpAndTypeHeaders(t *testing.T) {
	families := []MetricFamily{
		{Name: "test_metric", Help: "a test metric", Samples: []Sample{
			{Labels: []Label{{Name: "node", Value: "n1"}}, Value: 42},
		}},
	}
	output := Render(families)

	for _, want := range []string{
		"# HELP test_metric a test metric",
		"# TYPE test_metric gauge",
		`test_metric{node="n1"} 42`,
	} {
		if !strings.Contains(output, want) {
			t.Errorf("missing %q in output:\n%s", want, output)
		}
	}
}

func TestRender_MultipleLabels(t *testing.T) {
	families := []MetricFamily{
		{Name: "m", Help: "h", Samples: []Sample{
			{Labels: []Label{{Name: "a", Value: "1"}, {Name: "b", Value: "2"}}, Value: 1},
		}},
	}
	output := Render(families)
	if !strings.Contains(output, `m{a="1",b="2"} 1`) {
		t.Errorf("unexpected output:\n%s", output)
	}
}

func TestRender_EmptyFamilyNoSamples(t *testing.T) {
	families := []MetricFamily{
		{Name: "empty_metric", Help: "no data yet"},
	}
	output := Render(families)
	if strings.Contains(output, "empty_metric{") {
		t.Errorf("empty family should produce no sample lines:\n%s", output)
	}
	if !strings.Contains(output, "# HELP empty_metric") {
		t.Error("HELP header should still appear for empty family")
	}
}
