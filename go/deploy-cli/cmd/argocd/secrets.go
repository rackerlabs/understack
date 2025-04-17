package argocd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/rackerlabs/understack/go/deploy-cli/cmd"
	"github.com/rackerlabs/understack/go/deploy-cli/helpers"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/envutil"
	"github.com/gookit/goutil/fsutil"
	"github.com/spf13/cobra"
)

// Constants for file paths and template names
const (
	clusterSecretFile    = "secret-%s-cluster.yaml"
	secretDeployRepoFile = "secret-deploy-repo.yaml"
	argoNamespace        = "argocd"
)

// Templates as constants
const (
	argoSecretDeployRepoTemplate = `---
apiVersion: v1
kind: Secret
data:
  config: {{ .Config | b64enc }}
  name: {{ .Name | b64enc }}
  server: {{ .Server | b64enc }}
metadata:
  name: {{ .DEPLOY_NAME }}-cluster
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: cluster
    understack.rackspace.com/argocd: enabled
  annotations:
    uc_repo_git_url: "https://github.com/rackerlabs/understack.git"
    uc_repo_ref: "HEAD"
    uc_deploy_git_url: "{{ .UC_DEPLOY_GIT_URL }}"
    uc_deploy_ref: "HEAD"
    dns_zone: "{{ .DNS_ZONE }}"
`

	argoSecretClusterTemplate = `---
apiVersion: v1
kind: Secret
metadata:
  name: {{ .DEPLOY_NAME }}-repo
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repo-creds
data:
  sshPrivateKey: {{ .UC_DEPLOY_SSH_FILE }}
  type: {{ .Type | b64enc }}
  url: {{ .UC_DEPLOY_GIT_URL | b64enc }}
`
)

var ArgoCMD = &cobra.Command{
	Use:   "argocd-secrets",
	Short: "Generate ArgoCD secrets",
	Long:  "Generate repository and cluster secrets for ArgoCD deployment",
	Run: func(cmd *cobra.Command, args []string) {
		if err := GenerateSecrets(); err != nil {
			log.Fatal("Failed to generate secrets", "error", err)
			os.Exit(1)
		}
	},
}

func init() {
	cmd.RootCmd.AddCommand(ArgoCMD)
}

// GenerateSecrets orchestrates the generation of all ArgoCD secrets
func GenerateSecrets() error {
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
		"Name":              envutil.Getenv("UC_DEPLOY"),
		"Server":            "https://kubernetes.default.svc",
		"DEPLOY_NAME":       envutil.Getenv("DEPLOY_NAME"),
		"UC_DEPLOY_GIT_URL": envutil.Getenv("UC_DEPLOY_GIT_URL"),
		"DNS_ZONE":          envutil.Getenv("DNS_ZONE"),
	}

	result, err := helpers.TemplateHelper(argoSecretDeployRepoTemplate, vars)
	if err != nil {
		return fmt.Errorf("template rendering failed: %w", err)
	}

	filePath := filepath.Join(basePath, fmt.Sprintf(clusterSecretFile, envutil.Getenv("DEPLOY_NAME")))

	return writeToFile(filePath, result)
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

	result, err := helpers.TemplateHelper(argoSecretClusterTemplate, vars)
	if err != nil {
		return fmt.Errorf("template rendering failed: %w", err)
	}

	filePath := filepath.Join(basePath, secretDeployRepoFile)
	return writeToFile(filePath, result)
}

// writeToFile writes content to a file with proper permissions
func writeToFile(filePath string, content string) error {
	err := fsutil.WriteFile(filePath, content, os.ModePerm)
	if err != nil {
		return fmt.Errorf("file write failed: %w", err)
	}
	return nil
}
