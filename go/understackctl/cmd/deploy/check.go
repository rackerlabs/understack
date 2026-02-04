package deploy

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/charmbracelet/log"
	"github.com/spf13/cobra"
)

func newCmdDeployCheck() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "check <cluster-name>",
		Short: "Verify component manifests exist",
		Long:  `Check that kustomization.yaml and values.yaml exist for each enabled component.`,
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			clusterName := args[0]
			return runDeployCheck(clusterName)
		},
	}

	return cmd
}

func runDeployCheck(clusterName string) error {
	config, err := loadDeployConfig(clusterName)
	if err != nil {
		return err
	}

	components := enabledComponents(config)
	if len(components) == 0 {
		log.Info("No components enabled")
		return nil
	}

	missing := []string{}

	for _, comp := range components {
		compDir := filepath.Join(clusterName, comp)
		kustomPath := filepath.Join(compDir, "kustomization.yaml")
		valuesPath := filepath.Join(compDir, "values.yaml")

		if _, err := os.Stat(kustomPath); os.IsNotExist(err) {
			missing = append(missing, kustomPath)
		}

		if _, err := os.Stat(valuesPath); os.IsNotExist(err) {
			missing = append(missing, valuesPath)
		}
	}

	if len(missing) > 0 {
		log.Error("Missing required files:")
		for _, path := range missing {
			log.Errorf("  - %s", path)
		}
		return fmt.Errorf("validation failed: %d missing files", len(missing))
	}

	log.Infof("All %d components validated successfully", len(components))
	return nil
}
