package chartvalues

import (
	"sort"
	"testing"
)

const sampleValuesYAML = `
cluster_server: https://kubernetes.default.svc
understack_url: https://github.com/rackerlabs/understack.git
understack_ref: HEAD
deploy_url:
deploy_ref: HEAD
deploy_path_prefix:

global:
  enabled: true
  cert_manager:
    enabled: true
  cilium:
    enabled: true
  dex:
    enabled: true
  external_secrets:
    enabled: true

site:
  enabled: true
  cilium:
    enabled: true
  argo_events:
    enabled: true
  openstack:
    enabled: true
    repoUrl: https://tarballs.opendev.org/openstack/openstack-helm
    namespace: openstack
  keystone:
    enabled: true
    wave: 1
    chartVersion: "2025.2.7"
  snmp_exporter:
    enabled: true
  undersync:
    enabled: true
`

func sortComponentKeys(keys []ComponentKey) {
	sort.Slice(keys, func(i, j int) bool {
		return keys[i].Key < keys[j].Key
	})
}

func TestParseComponents(t *testing.T) {
	global, site, err := ParseComponents([]byte(sampleValuesYAML))
	if err != nil {
		t.Fatalf("ParseComponents failed: %v", err)
	}

	sortComponentKeys(global)
	sortComponentKeys(site)

	// Verify global components
	expectedGlobal := []ComponentKey{
		{Key: "cert_manager", Name: "cert-manager"},
		{Key: "cilium", Name: "cilium"},
		{Key: "dex", Name: "dex"},
		{Key: "external_secrets", Name: "external-secrets"},
	}

	if len(global) != len(expectedGlobal) {
		t.Fatalf("expected %d global components, got %d: %v", len(expectedGlobal), len(global), global)
	}

	for i, expected := range expectedGlobal {
		if global[i].Key != expected.Key {
			t.Errorf("global[%d].Key = %q, want %q", i, global[i].Key, expected.Key)
		}
		if global[i].Name != expected.Name {
			t.Errorf("global[%d].Name = %q, want %q", i, global[i].Name, expected.Name)
		}
	}

	// Verify site components
	expectedSite := []ComponentKey{
		{Key: "argo_events", Name: "argo-events"},
		{Key: "cilium", Name: "cilium"},
		{Key: "keystone", Name: "keystone"},
		{Key: "openstack", Name: "openstack"},
		{Key: "snmp_exporter", Name: "snmp-exporter"},
		{Key: "undersync", Name: "undersync"},
	}

	if len(site) != len(expectedSite) {
		t.Fatalf("expected %d site components, got %d: %v", len(expectedSite), len(site), site)
	}

	for i, expected := range expectedSite {
		if site[i].Key != expected.Key {
			t.Errorf("site[%d].Key = %q, want %q", i, site[i].Key, expected.Key)
		}
		if site[i].Name != expected.Name {
			t.Errorf("site[%d].Name = %q, want %q", i, site[i].Name, expected.Name)
		}
	}
}

func TestParseComponentsExcludesEnabled(t *testing.T) {
	global, site, err := ParseComponents([]byte(sampleValuesYAML))
	if err != nil {
		t.Fatalf("ParseComponents failed: %v", err)
	}

	for _, c := range global {
		if c.Key == "enabled" {
			t.Error("global components should not include 'enabled'")
		}
	}

	for _, c := range site {
		if c.Key == "enabled" {
			t.Error("site components should not include 'enabled'")
		}
	}
}

func TestParseComponentsUnderscoreToHyphen(t *testing.T) {
	global, _, err := ParseComponents([]byte(sampleValuesYAML))
	if err != nil {
		t.Fatalf("ParseComponents failed: %v", err)
	}

	for _, c := range global {
		if c.Key == "cert_manager" {
			if c.Name != "cert-manager" {
				t.Errorf("expected cert_manager -> cert-manager, got %q", c.Name)
			}
			return
		}
	}
	t.Error("cert_manager not found in global components")
}

func TestParseComponentsOpenStackIsComponent(t *testing.T) {
	_, site, err := ParseComponents([]byte(sampleValuesYAML))
	if err != nil {
		t.Fatalf("ParseComponents failed: %v", err)
	}

	found := false
	for _, c := range site {
		if c.Key == "openstack" {
			found = true
			if c.Name != "openstack" {
				t.Errorf("expected openstack -> openstack, got %q", c.Name)
			}
			break
		}
	}
	if !found {
		t.Error("openstack should be in site components")
	}
}

func TestParseComponentsEmptyInput(t *testing.T) {
	global, site, err := ParseComponents([]byte("{}"))
	if err != nil {
		t.Fatalf("ParseComponents failed: %v", err)
	}
	if len(global) != 0 {
		t.Errorf("expected 0 global components, got %d", len(global))
	}
	if len(site) != 0 {
		t.Errorf("expected 0 site components, got %d", len(site))
	}
}

func TestParseComponentsInvalidYAML(t *testing.T) {
	_, _, err := ParseComponents([]byte("not: valid: yaml: {{"))
	if err == nil {
		t.Error("expected error for invalid YAML")
	}
}
