package deploy

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/charmbracelet/log"
	"github.com/spf13/cobra"
	"sigs.k8s.io/kustomize/api/krusty"
	kusttypes "sigs.k8s.io/kustomize/api/types"
	"sigs.k8s.io/kustomize/kyaml/filesys"
)

func newCmdDeployCheck() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "check <cluster-name>",
		Short: "Verify component manifests exist and build",
		Long: `Check that kustomization.yaml and values.yaml exist for each enabled
component and that every kustomization.yaml builds successfully.`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			clusterName := args[0]
			return runDeployCheck(clusterName)
		},
	}

	return cmd
}

// kustomizeBuildOptions mirrors the kustomize.buildOptions configured in
// components/argocd/values.yaml so local validation matches ArgoCD's behaviour.
// It is the in-process equivalent of:
//
//	kustomize build --enable-alpha-plugins --enable-exec --enable-helm \
//	    --load-restrictor LoadRestrictionsNone
func kustomizeBuildOptions() *krusty.Options {
	opts := krusty.MakeDefaultOptions()
	// --load-restrictor LoadRestrictionsNone
	opts.LoadRestrictions = kusttypes.LoadRestrictionsNone
	// --enable-alpha-plugins, which also enables the helm chart inflator.
	// BploUseStaticallyLinked is what the kustomize CLI passes here; it makes
	// builtin plugins referenced from a "generators:" or "transformers:" field
	// resolve to their compiled-in implementations. BploLoadFromFileSys is
	// meant for kustomize's own development and would instead send them
	// looking for a plugin root under $KUSTOMIZE_PLUGIN_HOME.
	opts.PluginConfig = kusttypes.EnabledPluginConfig(kusttypes.BploUseStaticallyLinked)
	// EnabledPluginConfig defaults this to "helmV3", the CLI defaults to "helm".
	opts.PluginConfig.HelmConfig.Command = "helm"
	// --enable-exec
	opts.PluginConfig.FnpLoadingOptions.EnableExec = true
	return opts
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

	kustomizer := krusty.MakeKustomizer(kustomizeBuildOptions())
	fSys := filesys.MakeFsOnDisk()

	missing := []string{}
	buildErrors := []string{}

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

			if _, err := kustomizer.Run(fSys, compDir); err != nil {
				buildErrors = append(buildErrors, fmt.Sprintf("%s: %v", kustomPath, err))
			}
		}
	}

	if len(missing) > 0 {
		log.Error("Missing required files:")
		for _, path := range missing {
			log.Errorf("  - %s", path)
		}
	}

	if len(buildErrors) > 0 {
		log.Error("kustomize build failures:")
		for _, msg := range buildErrors {
			log.Errorf("  - %s", msg)
		}
	}

	if total := len(missing) + len(buildErrors); total > 0 {
		return fmt.Errorf("validation failed: %d error(s)", total)
	}

	log.Infof("All %d components validated successfully", len(components))
	return nil
}
