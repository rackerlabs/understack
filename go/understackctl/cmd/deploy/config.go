package deploy

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

func loadDeployConfig(clusterName string) (map[string]any, error) {
	deployYamlPath := filepath.Join(clusterName, "deploy.yaml")
	data, err := os.ReadFile(deployYamlPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read deploy.yaml: %w", err)
	}

	var config map[string]any
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse deploy.yaml: %w", err)
	}

	return config, nil
}

func saveDeployConfig(clusterName string, config map[string]any) error {
	deployYamlPath := filepath.Join(clusterName, "deploy.yaml")
	data, err := yaml.Marshal(config)
	if err != nil {
		return fmt.Errorf("failed to marshal deploy.yaml: %w", err)
	}

	if err := os.WriteFile(deployYamlPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write deploy.yaml: %w", err)
	}

	return nil
}

func enabledComponents(config map[string]any) []string {
	var components []string

	for _, section := range []string{"global", "site"} {
		if sectionRaw, ok := config[section]; ok {
			if sectionMap, ok := sectionRaw.(map[string]any); ok {
				if enabled, ok := sectionMap["enabled"].(bool); ok && enabled {
					for key, val := range sectionMap {
						if key == "enabled" {
							continue
						}
						if compMap, ok := val.(map[string]any); ok {
							if compEnabled, ok := compMap["enabled"].(bool); ok && compEnabled {
								components = append(components, strings.ReplaceAll(key, "_", "-"))
							}
						}
					}
				}
			}
		}
	}

	return components
}
