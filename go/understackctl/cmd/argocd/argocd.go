package argocd

import (
	_ "embed"
	"fmt"
	"os"
	"path/filepath"

	"github.com/rackerlabs/understack/go/understackctl/helpers"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/envutil"
	"github.com/gookit/goutil/fsutil"
	"github.com/spf13/cobra"
)

//go:embed templates/argoCluster.tmpl
var argoClusterTemplate string

//go:embed templates/argoSecretDeployRepo.tmpl
var argoSecretDeployRepoTemplate string

// Constants for file paths and template names
const (
	clusterSecretFile    = "secret-%s-cluster.yaml"
	secretDeployRepoFile = "secret-deploy-repo.yaml"
	argoNamespace        = "argocd"
)

func NewCmdArgocdSecret() *cobra.Command {
	return &cobra.Command{
		Use:   "argocd-secrets",
		Short: "Generate ArgoCD secrets",
		Long:  "Generate repository and cluster secrets for ArgoCD deployment",
		Run: func(cmd *cobra.Command, args []string) {
			if err := generateSecrets(); err != nil {
				log.Fatal("Failed to generate secrets", "error", err)
				os.Exit(1)
			}
		},
	}
}

// generateSecrets orchestrates the generation of all ArgoCD secrets
func generateSecrets() error {
	basePath := helpers.GetManifestPathToService("argocd")

	if err := generateDeployRepoSecret(basePath); err != nil {
		return fmt.Errorf("deploy repo secret generation failed: %w", err)
	}

	if err := generateClusterSecret(basePath); err != nil {
		return fmt.Errorf("cluster secret generation failed: %w", err)
	}

	helpers.UpdateKustomizeFile(basePath)
	return nil
}

// generateDeployRepoSecret generates the repository deployment secret
func generateDeployRepoSecret(basePath string) error {
	vars := map[string]any{
		"Config":            `{"tlsClientConfig":{"insecure":false}}`,
		"Name":              envutil.Getenv("DEPLOY_NAME"),
		"Server":            "https://kubernetes.default.svc",
		"DEPLOY_NAME":       envutil.Getenv("DEPLOY_NAME"),
		"UC_DEPLOY_GIT_URL": envutil.Getenv("UC_DEPLOY_GIT_URL"),
		"DNS_ZONE":          envutil.Getenv("DNS_ZONE"),
	}

	result, err := helpers.TemplateHelper(argoSecretDeployRepoTemplate, vars)
	if err != nil {
		return fmt.Errorf("template rendering failed: %w", err)
	}

	outputFilePath := filepath.Join(basePath, fmt.Sprintf(clusterSecretFile, envutil.Getenv("DEPLOY_NAME")))

	return writeToFile(outputFilePath, result)
}

// generateClusterSecret generates the cluster secret
func generateClusterSecret(basePath string) error {
	vars := map[string]any{
		"DEPLOY_NAME":        envutil.Getenv("DEPLOY_NAME"),
		"Type":               "git",
		"UC_DEPLOY_GIT_URL":  envutil.Getenv("UC_DEPLOY_GIT_URL"),
		"DNS_ZONE":           envutil.Getenv("DNS_ZONE"),
		"UC_DEPLOY_SSH_FILE": envutil.Getenv("UC_DEPLOY_SSH_FILE"),
	}

	result, err := helpers.TemplateHelper(argoClusterTemplate, vars)
	if err != nil {
		return fmt.Errorf("template rendering failed: %w", err)
	}

	outputFilePath := filepath.Join(basePath, secretDeployRepoFile)
	return writeToFile(outputFilePath, result)
}

// writeToFile writes content to a file with proper permissions
func writeToFile(filePath string, content string) error {
	err := fsutil.WriteFile(filePath, content, os.ModePerm)
	if err != nil {
		return fmt.Errorf("file write failed: %w", err)
	}
	return nil
}
