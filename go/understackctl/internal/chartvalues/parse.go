package chartvalues

import (
	"fmt"
	"io"
	"net/http"
	"strings"

	"gopkg.in/yaml.v3"
)

const (
	rawGitHubURL = "https://raw.githubusercontent.com/rackerlabs/understack/refs"
)

// ComponentKey represents a component found in the values.yaml.
type ComponentKey struct {
	Key  string // original key, e.g. "cert_manager"
	Name string // hyphenated name, e.g. "cert-manager"
}

// FetchValues fetches the ArgoCD chart values.yaml from GitHub for the given version.
// Version can be a branch name (e.g. "main") or a tag (e.g. "v0.1.6").
func FetchValues(version string) ([]byte, error) {
	refType := "heads"
	if strings.HasPrefix(version, "v") {
		refType = "tags"
	}

	url := fmt.Sprintf("%s/%s/%s/charts/argocd-understack/values.yaml", rawGitHubURL, refType, version)

	resp, err := http.Get(url)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch values.yaml: %w", err)
	}
	defer func() {
		_ = resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed to fetch values.yaml: HTTP %d from %s", resp.StatusCode, url)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	return data, nil
}

// knownNonComponents are keys under global/site that are not component names.
var knownNonComponents = map[string]bool{
	"enabled": true,
}

// ParseComponents extracts component keys from the global and site blocks of values.yaml.
// It returns separate lists for global and site components.
func ParseComponents(valuesYAML []byte) (global []ComponentKey, site []ComponentKey, err error) {
	var values map[string]any
	if err := yaml.Unmarshal(valuesYAML, &values); err != nil {
		return nil, nil, fmt.Errorf("failed to parse values.yaml: %w", err)
	}

	global, err = extractComponents(values, "global")
	if err != nil {
		return nil, nil, fmt.Errorf("failed to extract global components: %w", err)
	}

	site, err = extractComponents(values, "site")
	if err != nil {
		return nil, nil, fmt.Errorf("failed to extract site components: %w", err)
	}

	return global, site, nil
}

// extractComponents walks a scope block (global or site) and returns component keys.
func extractComponents(values map[string]any, scope string) ([]ComponentKey, error) {
	scopeRaw, ok := values[scope]
	if !ok {
		return nil, nil
	}

	scopeMap, ok := scopeRaw.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("%s is not a map", scope)
	}

	var components []ComponentKey
	for key := range scopeMap {
		if knownNonComponents[key] {
			continue
		}

		// Verify this key maps to a map (component config block)
		child, ok := scopeMap[key]
		if !ok {
			continue
		}
		if _, isMap := child.(map[string]any); !isMap {
			continue
		}

		components = append(components, ComponentKey{
			Key:  key,
			Name: strings.ReplaceAll(key, "_", "-"),
		})
	}

	return components, nil
}
