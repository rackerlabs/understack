package nautobot

import (
	"fmt"
	"io/fs"
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
