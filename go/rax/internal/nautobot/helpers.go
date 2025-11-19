package nautobot

import (
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"

	nb "github.com/nautobot/go-nautobot/v2"
	"go.yaml.in/yaml/v3"
)

func ListYAMLFiles(dir string) ([]string, error) {
	var files []string

	err := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return fmt.Errorf("error accessing %s: %w", path, err)
		}

		if d.IsDir() {
			return nil
		}

		ext := filepath.Ext(path)
		if ext == ".yaml" || ext == ".yml" {
			files = append(files, path)
		}
		return nil
	})

	if err != nil {
		return nil, err
	}

	return files, nil
}

func ParseYAMLToStruct[T any](path string) (T, error) {
	var result T

	data, err := os.ReadFile(path)
	if err != nil {
		return result, fmt.Errorf("failed to read file %s: %w", path, err)
	}

	if err := yaml.Unmarshal(data, &result); err != nil {
		return result, fmt.Errorf("failed to parse YAML %s: %w", path, err)
	}

	return result, nil
}

func buildBulkWritableCableRequestStatus(uuid string) *nb.BulkWritableCableRequestStatus {
	return &nb.BulkWritableCableRequestStatus{
		Id: &nb.BulkWritableCableRequestStatusId{
			String: nb.PtrString(uuid),
		},
	}
}

func buildNullableBulkWritableCircuitRequestTenant(uuid string) nb.NullableBulkWritableCircuitRequestTenant {
	return *nb.NewNullableBulkWritableCircuitRequestTenant(&nb.BulkWritableCircuitRequestTenant{
		Id: &nb.BulkWritableCableRequestStatusId{
			String: nb.PtrString(uuid),
		},
	})
}

func buildNullableBulkWritableRackRequestRackGroup(uuid string) *nb.NullableBulkWritableRackRequestRackGroup {
	return nb.NewNullableBulkWritableRackRequestRackGroup(&nb.BulkWritableRackRequestRackGroup{
		Id: &nb.BulkWritableCableRequestStatusId{
			String: nb.PtrString(uuid),
		},
	})
}

// readResponseBody safely reads and closes the response body.
// Returns the body content as a string. If resp is nil, returns empty string.
func readResponseBody(resp *http.Response) string {
	if resp == nil || resp.Body == nil {
		return ""
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Sprintf("failed to read response body: %v", err)
	}
	return string(bodyBytes)
}
