package deploy

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/spf13/cobra"
)

const (
	defaultChartURL = "https://github.com/rackerlabs/understack//charts/argocd-understack"
)

func newCmdDeployRender() *cobra.Command {
	var chartPath string
	var valuesFile string
	var version string

	cmd := &cobra.Command{
		Use:   "render <cluster-name>",
		Short: "Preview rendered ArgoCD Applications via helm template",
		Long: `Render the ArgoCD Applications Helm chart for a cluster, printing
the rendered YAML to stdout. This is a convenience wrapper around
helm template.`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			clusterName := args[0]
			return runDeployRender(clusterName, chartPath, valuesFile, version)
		},
	}

	cmd.Flags().StringVar(&chartPath, "chart-path", "", "Path or URL to the ArgoCD Helm chart (default: UnderStack GitHub repo)")
	cmd.Flags().StringVarP(&valuesFile, "values", "f", "", "Path to the per-cluster values file (default: <cluster-name>/values.yaml)")
	cmd.Flags().StringVar(&version, "version", "main", "Chart version (branch/tag) when using the default git chart URL")

	return cmd
}

func runDeployRender(clusterName, chartPath, valuesFile, version string) error {
	if chartPath == "" {
		chartPath = defaultChartURL + "?ref=" + version
	}

	if valuesFile == "" {
		valuesFile = filepath.Join(clusterName, "values.yaml")
	}

	if _, err := os.Stat(valuesFile); err != nil {
		return fmt.Errorf("values file not found: %s", valuesFile)
	}

	helmPath, err := exec.LookPath("helm")
	if err != nil {
		return fmt.Errorf("helm not found in PATH: %w", err)
	}

	args := []string{
		"template",
		clusterName,
		chartPath,
		"-f", valuesFile,
	}

	helmCmd := exec.Command(helmPath, args...)
	helmCmd.Stdout = os.Stdout
	helmCmd.Stderr = os.Stderr

	if err := helmCmd.Run(); err != nil {
		return fmt.Errorf("helm template failed: %w", err)
	}

	return nil
}
