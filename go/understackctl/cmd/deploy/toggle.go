package deploy

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/log"
	"github.com/spf13/cobra"
)

func newCmdDeployEnable() *cobra.Command {
	var componentType string

	cmd := &cobra.Command{
		Use:   "enable <cluster-name> <name>",
		Short: "Enable a component in deploy.yaml",
		Args:  cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			clusterName := args[0]
			name := args[1]
			return runDeployEnable(clusterName, name, componentType)
		},
	}

	cmd.Flags().StringVar(&componentType, "type", "", "Component type: global, site, or aio")
	if err := cmd.MarkFlagRequired("type"); err != nil {
		log.Warnf("Could not mark --type as required: %v", err)
	}

	return cmd
}

func newCmdDeployDisable() *cobra.Command {
	var componentType string

	cmd := &cobra.Command{
		Use:   "disable <cluster-name> <name>",
		Short: "Disable a component in deploy.yaml",
		Args:  cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			clusterName := args[0]
			name := args[1]
			return runDeployDisable(clusterName, name, componentType)
		},
	}

	cmd.Flags().StringVar(&componentType, "type", "", "Component type: global, site, or aio")
	if err := cmd.MarkFlagRequired("type"); err != nil {
		log.Warnf("Could not mark --type as required: %v", err)
	}

	return cmd
}

func runDeployEnable(clusterName, name, componentType string) error {
	if err := validateDeployType(componentType, deployTypeGlobal, deployTypeSite, deployTypeAIO); err != nil {
		return err
	}

	config, err := loadDeployConfig(clusterName)
	if err != nil {
		return err
	}

	for _, sectionName := range deployTargetSections(componentType) {
		section, ok := config[sectionName].(map[string]any)
		if !ok {
			section = map[string]any{}
			config[sectionName] = section
		}

		section["enabled"] = true
		section[normalizeDeployComponentName(name)] = map[string]any{"enabled": true}
	}

	if err := saveDeployConfig(clusterName, config); err != nil {
		return err
	}

	log.Infof("Enabled %s in %s for %s", name, componentType, clusterName)
	return nil
}

func runDeployDisable(clusterName, name, componentType string) error {
	if err := validateDeployType(componentType, deployTypeGlobal, deployTypeSite, deployTypeAIO); err != nil {
		return err
	}

	config, err := loadDeployConfig(clusterName)
	if err != nil {
		return err
	}

	for _, sectionName := range deployTargetSections(componentType) {
		section, ok := config[sectionName].(map[string]any)
		if !ok {
			return fmt.Errorf("missing %s section in deploy.yaml", sectionName)
		}

		section[normalizeDeployComponentName(name)] = map[string]any{"enabled": false}
	}

	if err := saveDeployConfig(clusterName, config); err != nil {
		return err
	}

	log.Infof("Disabled %s in %s for %s", name, componentType, clusterName)
	return nil
}

func normalizeDeployComponentName(name string) string {
	return strings.ReplaceAll(name, "-", "_")
}

func deployTargetSections(componentType string) []string {
	if componentType == deployTypeAIO {
		return []string{deployTypeGlobal, deployTypeSite}
	}

	return []string{componentType}
}
