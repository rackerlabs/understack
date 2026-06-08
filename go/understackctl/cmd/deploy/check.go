package deploy

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/log"
	"github.com/spf13/cobra"
)

// kustomizeBuildArgs mirrors the kustomize.buildOptions configured in
// components/argocd/values.yaml so local validation matches ArgoCD's behaviour.
var kustomizeBuildArgs = []string{
	"--enable-alpha-plugins",
	"--enable-exec",
	"--enable-helm",
	"--load-restrictor", "LoadRestrictionsNone",
}

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

	kustomizePath, err := exec.LookPath("kustomize")
	if err != nil {
		log.Warn("kustomize not found in PATH, skipping kustomization.yaml validation")
		kustomizePath = ""
	}

	missing := []string{}
	var kustomizeErrors []string

	for _, comp := range components {
		compDir := filepath.Join(clusterName, comp.Name)

		if comp.InstallApp {
			valuesPath := filepath.Join(compDir, "values.yaml")
			if _, err := os.Stat(valuesPath); os.IsNotExist(err) {
				missing = append(missing, valuesPath)
			}
		}

		if comp.InstallConfigs {
			kustomPath := filepath.Join(compDir, "kustomization.yaml")
			if _, err := os.Stat(kustomPath); os.IsNotExist(err) {
				missing = append(missing, kustomPath)
				continue
			}

			if kustomizePath != "" {
				args := append(append([]string{"build"}, kustomizeBuildArgs...), compDir)
				out, err := exec.Command(kustomizePath, args...).CombinedOutput()
				if err != nil {
					kustomizeErrors = append(kustomizeErrors,
						fmt.Sprintf("%s: %s", kustomPath, strings.TrimSpace(string(out))))
				}
			}
		}
	}

	if len(missing) > 0 {
		log.Error("Missing required files:")
		for _, path := range missing {
			log.Errorf("  - %s", path)
		}
	}

	if len(kustomizeErrors) > 0 {
		log.Error("kustomize build failures:")
		for _, msg := range kustomizeErrors {
			log.Errorf("  - %s", msg)
		}
	}

	if total := len(missing) + len(kustomizeErrors); total > 0 {
		return fmt.Errorf("validation failed: %d error(s)", total)
	}

	log.Infof("All %d components validated successfully", len(components))
	return nil
}
