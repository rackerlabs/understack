package deploy

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestDeployConfigStructure(t *testing.T) {
	config := map[string]any{
		"understack_url": understackRepoURL,
		"deploy_url":     "https://github.com/example/deploy.git",
		"global": map[string]any{
			"enabled": true,
			"cert_manager": map[string]any{
				"enabled": true,
			},
			"external_secrets": map[string]any{
				"enabled": false,
			},
		},
		"site": map[string]any{
			"enabled": true,
			"keystone": map[string]any{
				"enabled": true,
			},
		},
	}

	data, err := yaml.Marshal(&config)
	if err != nil {
		t.Fatalf("failed to marshal config: %v", err)
	}

	var parsed map[string]any
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("failed to unmarshal config: %v", err)
	}

	globalMap := parsed["global"].(map[string]any)
	certMgr := globalMap["cert_manager"].(map[string]any)
	if !certMgr["enabled"].(bool) {
		t.Error("cert_manager should be enabled")
	}
}

func TestEnabledComponentsConvertsToHyphens(t *testing.T) {
	config := map[string]any{
		"global": map[string]any{
			"enabled": true,
			"cert_manager": map[string]any{
				"enabled": true,
			},
			"external_secrets": map[string]any{
				"enabled": true,
			},
		},
		"site": map[string]any{
			"enabled": true,
			"argo_workflows": map[string]any{
				"enabled": true,
			},
			"mariadb_operator": map[string]any{
				"enabled": false,
			},
		},
	}

	components := enabledComponents(config)

	expected := map[string]bool{
		"cert-manager":      true,
		"external-secrets":  true,
		"argo-workflows":    true,
	}

	if len(components) != len(expected) {
		t.Fatalf("expected %d components, got %d", len(expected), len(components))
	}

	for _, comp := range components {
		if !expected[comp] {
			t.Errorf("unexpected component: %s", comp)
		}
	}
}

func TestDeployInit(t *testing.T) {
	tmpDir := t.TempDir()
	clusterName := filepath.Join(tmpDir, "test-cluster")

	if err := runDeployInit(clusterName, "site", "origin"); err != nil {
		t.Fatalf("runDeployInit failed: %v", err)
	}

	deployYaml := filepath.Join(clusterName, "deploy.yaml")
	if _, err := os.Stat(deployYaml); os.IsNotExist(err) {
		t.Fatal("deploy.yaml was not created")
	}

	data, err := os.ReadFile(deployYaml)
	if err != nil {
		t.Fatalf("failed to read deploy.yaml: %v", err)
	}

	var config map[string]any
	if err := yaml.Unmarshal(data, &config); err != nil {
		t.Fatalf("failed to parse deploy.yaml: %v", err)
	}

	if config["understack_url"] != understackRepoURL {
		t.Errorf("unexpected understack_url: %s", config["understack_url"])
	}

	if _, ok := config["global"]; ok {
		t.Error("global should not be set for site type")
	}

	siteMap, ok := config["site"].(map[string]any)
	if !ok || !siteMap["enabled"].(bool) {
		t.Error("site should be enabled")
	}

	// Check that components are present as individual keys
	componentCount := 0
	for key := range siteMap {
		if key != "enabled" {
			componentCount++
		}
	}

	if componentCount == 0 {
		t.Error("site should have component keys")
	}
}

func TestDeployUpdate(t *testing.T) {
	tmpDir := t.TempDir()
	clusterName := filepath.Join(tmpDir, "test-cluster")

	config := map[string]any{
		"understack_url": understackRepoURL,
		"site": map[string]any{
			"enabled": true,
			"keystone": map[string]any{
				"enabled": true,
			},
			"nova_compute": map[string]any{
				"enabled": true,
			},
		},
	}

	if err := os.MkdirAll(clusterName, 0755); err != nil {
		t.Fatalf("failed to create cluster dir: %v", err)
	}

	data, err := yaml.Marshal(&config)
	if err != nil {
		t.Fatalf("failed to marshal config: %v", err)
	}

	deployYaml := filepath.Join(clusterName, "deploy.yaml")
	if err := os.WriteFile(deployYaml, data, 0644); err != nil {
		t.Fatalf("failed to write deploy.yaml: %v", err)
	}

	if err := runDeployUpdate(clusterName); err != nil {
		t.Fatalf("runDeployUpdate failed: %v", err)
	}

	keystoneDir := filepath.Join(clusterName, "keystone")
	novaDir := filepath.Join(clusterName, "nova-compute")

	for _, dir := range []string{keystoneDir, novaDir} {
		kustomPath := filepath.Join(dir, "kustomization.yaml")
		valuesPath := filepath.Join(dir, "values.yaml")

		if _, err := os.Stat(kustomPath); os.IsNotExist(err) {
			t.Errorf("kustomization.yaml not created in %s", dir)
		}

		if _, err := os.Stat(valuesPath); os.IsNotExist(err) {
			t.Errorf("values.yaml not created in %s", dir)
		}
	}
}

func TestDeployCheck(t *testing.T) {
	tmpDir := t.TempDir()
	clusterName := filepath.Join(tmpDir, "test-cluster")

	config := map[string]any{
		"site": map[string]any{
			"enabled": true,
			"keystone": map[string]any{
				"enabled": true,
			},
		},
	}

	if err := os.MkdirAll(clusterName, 0755); err != nil {
		t.Fatalf("failed to create cluster dir: %v", err)
	}

	data, err := yaml.Marshal(&config)
	if err != nil {
		t.Fatalf("failed to marshal config: %v", err)
	}

	deployYaml := filepath.Join(clusterName, "deploy.yaml")
	if err := os.WriteFile(deployYaml, data, 0644); err != nil {
		t.Fatalf("failed to write deploy.yaml: %v", err)
	}

	if err := runDeployCheck(clusterName); err == nil {
		t.Error("check should fail when components don't exist")
	}

	keystoneDir := filepath.Join(clusterName, "keystone")
	if err := os.MkdirAll(keystoneDir, 0755); err != nil {
		t.Fatalf("failed to create keystone dir: %v", err)
	}

	kustomPath := filepath.Join(keystoneDir, "kustomization.yaml")
	valuesPath := filepath.Join(keystoneDir, "values.yaml")

	if err := os.WriteFile(kustomPath, []byte("test"), 0644); err != nil {
		t.Fatalf("failed to write kustomization.yaml: %v", err)
	}

	if err := os.WriteFile(valuesPath, []byte("test"), 0644); err != nil {
		t.Fatalf("failed to write values.yaml: %v", err)
	}

	if err := runDeployCheck(clusterName); err != nil {
		t.Errorf("check should pass: %v", err)
	}
}

func TestDeployWorkflowIntegration(t *testing.T) {
	tmpDir := t.TempDir()
	clusterName := filepath.Join(tmpDir, "integration-test")

	if err := runDeployInit(clusterName, "site", "origin"); err != nil {
		t.Fatalf("init failed: %v", err)
	}

	config, err := loadDeployConfig(clusterName)
	if err != nil {
		t.Fatalf("failed to load config: %v", err)
	}

	siteMap, ok := config["site"].(map[string]any)
	if !ok || !siteMap["enabled"].(bool) {
		t.Fatal("site should be enabled")
	}

	if err := runDeployUpdate(clusterName); err != nil {
		t.Fatalf("update failed: %v", err)
	}

	components := enabledComponents(config)
	for _, comp := range components {
		compDir := filepath.Join(clusterName, comp)
		if _, err := os.Stat(compDir); os.IsNotExist(err) {
			t.Errorf("directory not created for component: %s", comp)
		}
	}

	if err := runDeployCheck(clusterName); err != nil {
		t.Fatalf("check failed: %v", err)
	}

	// Modify config to only have keystone and nova
	config["site"] = map[string]any{
		"enabled": true,
		"keystone": map[string]any{
			"enabled": true,
		},
		"nova": map[string]any{
			"enabled": true,
		},
	}

	data, err := yaml.Marshal(&config)
	if err != nil {
		t.Fatalf("failed to marshal config: %v", err)
	}

	deployYaml := filepath.Join(clusterName, "deploy.yaml")
	if err := os.WriteFile(deployYaml, data, 0644); err != nil {
		t.Fatalf("failed to write deploy.yaml: %v", err)
	}

	if err := runDeployUpdate(clusterName); err != nil {
		t.Fatalf("update after config change failed: %v", err)
	}

	entries, err := os.ReadDir(clusterName)
	if err != nil {
		t.Fatalf("failed to read cluster dir: %v", err)
	}

	// Count only component directories (not deploy.yaml)
	compCount := 0
	for _, entry := range entries {
		if entry.IsDir() {
			compCount++
		}
	}

	if compCount != 2 {
		t.Errorf("expected 2 component directories, got %d", compCount)
	}

	if err := runDeployCheck(clusterName); err != nil {
		t.Fatalf("check after cleanup failed: %v", err)
	}
}
