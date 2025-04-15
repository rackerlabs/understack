package helpers

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/fsutil"
)

const kustomizationFile = "kustomization.yaml"

func UpdateKustomizeFile(dir string) {
	files, err := scanYamlFiles(dir)
	if err != nil {
		log.Fatalf("Error scanning directory: %v", err)
	}

	if len(files) == 0 {
		log.Info("No YAML files found to include in kustomization.yaml")
		return
	}

	kustomization := buildKustomizationYAML(files)

	kustomPath := filepath.Join(dir, kustomizationFile)
	err = os.WriteFile(kustomPath, []byte(kustomization), 0644)
	if err != nil {
		log.Fatalf("Error writing kustomization.yaml: %v", err)
	}

	log.Printf("Successfully wrote %s with %d resources.\n", kustomPath, len(files))
}

func scanYamlFiles(dir string) ([]string, error) {
	fileSet := make(map[string]bool)

	fsutil.FindInDir(dir, func(filePath string, de fs.DirEntry) error {
		fileSet[de.Name()] = true
		return nil
	}, fsutil.IncludeSuffix(".yaml", ".yml"),
		fsutil.ExcludeDotFile,
		fsutil.ExcludeNames(kustomizationFile))

	var uniqueFiles []string
	for f := range fileSet {
		uniqueFiles = append(uniqueFiles, f)
	}
	sort.Strings(uniqueFiles)
	return uniqueFiles, nil
}

func buildKustomizationYAML(resources []string) string {
	var sb strings.Builder
	sb.WriteString("apiVersion: kustomize.config.k8s.io/v1beta1\n")
	sb.WriteString("kind: Kustomization\n")
	sb.WriteString("resources:\n")
	for _, res := range resources {
		sb.WriteString(fmt.Sprintf("- %s\n", res))
	}
	return sb.String()
}
