package dex

import (
	"fmt"
	"path/filepath"

	"github.com/rackerlabs/understack/go/understack/cmd"
	"github.com/rackerlabs/understack/go/understack/helpers"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/envutil"

	"github.com/spf13/cobra"
)

func init() {
	cmd.DeployCmd.AddCommand(Dex)
}

var Dex = &cobra.Command{
	Use:   "dex-secrets",
	Short: "Create dex secret for nautobot, argo, argocd, keystone, grafana",
	Long:  "Create dex secret for nautobot, argo, argocd, keystone, grafana",
	Run:   generateDexSecrets,
}

func generateDexSecrets(cmd *cobra.Command, args []string) {
	if err := generateDexServiceSecrets(); err != nil {
		log.Error("Failed to generate secrets for dex", "err", err)
	}
}

// credGen prints out the cli version number
func generateDexServiceSecrets() error {
	clients := []string{"nautobot", "argo", "argocd", "keystone", "grafana"}

	manifestPath := helpers.GetManifestPathToService("dex")

	for _, client := range clients {

		config := helpers.SecretConfig{
			Name:      fmt.Sprintf("%s-sso", client),
			Namespace: "dex",
			Data: map[string]string{
				"client-secret": helpers.GenerateRandomString(32),
				"client-id":     client,
				"issuer":        fmt.Sprintf("https://dex.%s", envutil.Getenv("DNS_ZONE")),
			},
		}

		outputFilePath := manifestPath + fmt.Sprintf("/secret-%s-sso-dex.yaml", client)

		if err := helpers.CreateKubeSealSecretFile(config, outputFilePath); err != nil {
			return err
		}
	}

	helpers.UpdateKustomizeFile(filepath.Join(envutil.Getenv("DEPLOY_NAME"), "manifests", "dex"))

	return nil
}
