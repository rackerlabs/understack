package deploy

import (
	"bytes"
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
	return writeYAMLFile(deployYamlPath, config)
}

func writeYAMLFile(path string, value any) error {
	var buf bytes.Buffer
	enc := yaml.NewEncoder(&buf)
	enc.SetIndent(2)
	if err := enc.Encode(value); err != nil {
		_ = enc.Close()
		return fmt.Errorf("failed to marshal YAML: %w", err)
	}
	if err := enc.Close(); err != nil {
		return fmt.Errorf("failed to finalize YAML encoding: %w", err)
	}

	if err := os.WriteFile(path, buf.Bytes(), 0644); err != nil {
		return fmt.Errorf("failed to write YAML file %s: %w", path, err)
	}

	return nil
}

// ComponentConfig holds the name and deploy options for an enabled component.
type ComponentConfig struct {
	Name           string
	InstallApp     bool
	InstallConfigs bool
}

func enabledComponents(config map[string]any) []ComponentConfig {
	var components []ComponentConfig

	for _, section := range []string{"global", "site"} {
		if sectionRaw, ok := config[section]; ok {
			if sectionMap, ok := sectionRaw.(map[string]any); ok {
				if enabled, ok := sectionMap["enabled"].(bool); ok && enabled {
					for key, val := range sectionMap {
						if key == "enabled" {
							continue
						}
						if compMap, ok := val.(map[string]any); ok {
							compEnabled := boolOption(compMap, "enabled", false)
							installApp := boolOption(compMap, "installApp", compEnabled)
							installConfigs := boolOption(compMap, "installConfigs", compEnabled)
							if compEnabled || installApp || installConfigs {
								components = append(components, ComponentConfig{
									Name:           strings.ReplaceAll(key, "_", "-"),
									InstallApp:     installApp,
									InstallConfigs: installConfigs,
								})
							}
						}
					}
				}
			}
		}
	}

	return components
}

func boolOption(m map[string]any, key string, defaultVal bool) bool {
	if v, ok := m[key].(bool); ok {
		return v
	}
	return defaultVal
}
