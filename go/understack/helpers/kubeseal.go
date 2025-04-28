package helpers

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/fsutil"
)

func KubeSeal(inputData []byte, outputPath string) error {
	// Convert secret to YAML first
	tmpFile, err := os.CreateTemp("", "secret-*.yaml")
	if err != nil {
		return err
	}
	defer removeTempFile(tmpFile)

	if _, err := tmpFile.Write([]byte(inputData)); err != nil {
		return err
	}
	if err := tmpFile.Close(); err != nil {
		return err
	}

	cmd := exec.Command("kubeseal",
		"--scope", "cluster-wide",
		"--allow-empty-data",
		"--format", "yaml",
	)
	// Set up stdin
	cmd.Stdin, err = os.Open(tmpFile.Name())
	if err != nil {
		return err
	}

	// Capture output
	var out bytes.Buffer
	cmd.Stdout = &out

	// Run command
	err = cmd.Run()
	if err != nil {
		log.Info("err", "err", err)
		return fmt.Errorf("kubeseal failed: %v", err)
	}

	err = fsutil.WriteFile(outputPath, out.String(), os.ModePerm)
	if err != nil {
		log.Fatal("error in kustomization.yaml file", "err", err)
	}
	return nil
}

func removeTempFile(file *os.File) {
    if err := os.Remove(file.Name()); err != nil {
        log.Printf("Failed to remove temporary file: %v", err)
    }
}
