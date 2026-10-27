package deploy

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/log"
	"github.com/spf13/cobra"
	"sigs.k8s.io/kustomize/api/krusty"
	kusttypes "sigs.k8s.io/kustomize/api/types"
	"sigs.k8s.io/kustomize/kyaml/filesys"
)

// validateKustomization runs the equivalent of
//
//	kustomize build --enable-alpha-plugins --enable-exec --enable-helm \
//	    --load-restrictor LoadRestrictionsNone <compDir>
//
// which mirrors the kustomize.buildOptions configured in
// components/argocd/values.yaml so local validation matches ArgoCD's behaviour.
//
// The build runs against the kustomize library version pinned in go.mod, not
// the kustomize bundled with ArgoCD. Keep the two reasonably close, otherwise a
// kustomization may pass here and fail in ArgoCD (or the reverse).
func validateKustomization(compDir string) error {
	opts := krusty.MakeDefaultOptions()
	opts.LoadRestrictions = kusttypes.LoadRestrictionsNone
	opts.PluginConfig = kusttypes.EnabledPluginConfig(kusttypes.BploLoadFromFileSys)
	opts.PluginConfig.HelmConfig.Command = "helm"
	opts.PluginConfig.FnpLoadingOptions.EnableExec = true

	_, err := krusty.MakeKustomizer(opts).Run(filesys.MakeFsOnDisk(), compDir)
	if err != nil && strings.Contains(err.Error(), "helm") {
		if _, lookErr := exec.LookPath("helm"); lookErr != nil {
			return fmt.Errorf("%w (the helm binary was not found in PATH; it is required to validate kustomizations that use helmCharts)", err)
		}
	}
	return err
}

// formatKustomizeError renders a build failure with the path on its own line
// and the (often long, multi-line) error indented beneath it.
func formatKustomizeError(path string, err error) string {
	var b strings.Builder
	b.WriteString(path)
	b.WriteString(":")
	for _, line := range strings.Split(strings.TrimSpace(err.Error()), "\n") {
		b.WriteString("\n      ")
		b.WriteString(strings.TrimSpace(line))
	}
	return b.String()
}

func newCmdDeployCheck() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "check <cluster-name>",
		Short: "Verify component manifests exist and build",
		Long: `Check that kustomization.yaml and values.yaml exist for each enabled component,
then build each kustomization.yaml in-process using the same options as ArgoCD
(alpha plugins, exec functions, helm, and no load restrictions).

Building may execute exec plugins and run helm, which requires the helm binary
in PATH and may access the network to fetch charts. Only run this against
checkouts you trust.`,
		Args: cobra.ExactArgs(1),
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
	var kustomizeErrors []string // pre-formatted by formatKustomizeError

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

			if err := validateKustomization(compDir); err != nil {
				kustomizeErrors = append(kustomizeErrors, formatKustomizeError(kustomPath, err))
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
