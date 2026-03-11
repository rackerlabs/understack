package deploy

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
)

const (
	defaultChartRepo = "https://github.com/rackerlabs/understack.git"
	defaultChartDir  = "charts/argocd-understack"
)

func newCmdDeployRender() *cobra.Command {
	var chartPath string
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
			return runDeployRender(clusterName, chartPath, version)
		},
	}

	cmd.Flags().StringVar(&chartPath, "chart-path", "", "Path to the ArgoCD Helm chart (default: clone understack repo and use charts/argocd-understack)")
	cmd.Flags().StringVar(&version, "version", "main", "Git ref (branch/tag) to use when cloning the default chart source")

	return cmd
}

func runDeployRender(clusterName, chartPath, version string) error {
	deployFile := filepath.Join(clusterName, "deploy.yaml")
	if _, err := os.Stat(deployFile); err != nil {
		return fmt.Errorf("deploy config file not found: %s", deployFile)
	}

	cleanup := func() {}
	if chartPath == "" {
		var err error
		chartPath, cleanup, err = defaultDeployRenderChartPath(clusterName, version)
		if err != nil {
			return err
		}
	}
	defer cleanup()

	helmPath, err := exec.LookPath("helm")
	if err != nil {
		return fmt.Errorf("helm not found in PATH: %w", err)
	}

	args := []string{
		"template",
		clusterName,
		chartPath,
		"-f", deployFile,
	}

	helmCmd := exec.Command(helmPath, args...)
	helmCmd.Stdout = os.Stdout
	helmCmd.Stderr = os.Stderr

	if err := helmCmd.Run(); err != nil {
		return fmt.Errorf("helm template failed: %w", err)
	}

	return nil
}

func defaultDeployRenderChartPath(clusterName, version string) (string, func(), error) {
	repoURL := defaultChartRepo
	if config, err := loadDeployConfig(clusterName); err == nil {
		if understackURL, ok := config["understack_url"].(string); ok && understackURL != "" {
			repoURL = understackURL
		}
	}

	tmpDir, err := os.MkdirTemp("", "understackctl-render-chart-*")
	if err != nil {
		return "", func() {}, fmt.Errorf("failed to create temp directory for chart checkout: %w", err)
	}

	cleanup := func() {
		_ = os.RemoveAll(tmpDir)
	}

	gitPath, err := exec.LookPath("git")
	if err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("git not found in PATH: %w", err)
	}

	cloneCmd := exec.Command(gitPath, "clone", "--depth", "1", "--branch", version, repoURL, tmpDir)
	output, err := cloneCmd.CombinedOutput()
	if err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("failed to clone %s at ref %s: %s", repoURL, version, strings.TrimSpace(string(output)))
	}

	chartPath := filepath.Join(tmpDir, defaultChartDir)
	if _, err := os.Stat(chartPath); err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("chart directory not found in cloned repo: %s", chartPath)
	}

	return chartPath, cleanup, nil
}
