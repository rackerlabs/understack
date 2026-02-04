package deploy

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/charmbracelet/log"
	"github.com/spf13/cobra"
)

const (
	kustomizationContent = `apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: []
`
	valuesContent = `# Component-specific Helm values
`
)

func newCmdDeployUpdate() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "update <cluster-name>",
		Short: "Sync components with deploy.yaml",
		Long:  `Add or remove component directories based on deploy.yaml configuration.`,
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			clusterName := args[0]
			return runDeployUpdate(clusterName)
		},
	}

	return cmd
}

func runDeployUpdate(clusterName string) error {
	config, err := loadDeployConfig(clusterName)
	if err != nil {
		return err
	}

	enabledComps := enabledComponents(config)
	enabledSet := make(map[string]bool)
	for _, comp := range enabledComps {
		enabledSet[comp] = true
	}

	// Remove disabled components
	entries, err := os.ReadDir(clusterName)
	if err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("failed to read cluster directory: %w", err)
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		if !enabledSet[entry.Name()] {
			compDir := filepath.Join(clusterName, entry.Name())
			if err := os.RemoveAll(compDir); err != nil {
				return fmt.Errorf("failed to remove %s: %w", compDir, err)
			}
			log.Infof("Removed %s", compDir)
		}
	}

	// Add enabled components and ensure files exist
	created := 0
	for _, comp := range enabledComps {
		compDir := filepath.Join(clusterName, comp)
		kustomPath := filepath.Join(compDir, "kustomization.yaml")
		valuesPath := filepath.Join(compDir, "values.yaml")

		dirExists := false
		if _, err := os.Stat(compDir); err == nil {
			dirExists = true
		}

		if err := os.MkdirAll(compDir, 0755); err != nil {
			return fmt.Errorf("failed to create directory %s: %w", compDir, err)
		}

		if _, err := os.Stat(kustomPath); os.IsNotExist(err) {
			if err := os.WriteFile(kustomPath, []byte(kustomizationContent), 0644); err != nil {
				return fmt.Errorf("failed to write %s: %w", kustomPath, err)
			}
		}

		if _, err := os.Stat(valuesPath); os.IsNotExist(err) {
			if err := os.WriteFile(valuesPath, []byte(valuesContent), 0644); err != nil {
				return fmt.Errorf("failed to write %s: %w", valuesPath, err)
			}
		}

		if !dirExists {
			log.Infof("Created %s", compDir)
			created++
		}
	}

	log.Infof("Updated components: %d created", created)
	return nil
}
