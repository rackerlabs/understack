package certManager

import (
	_ "embed"
	"fmt"
	"os"

	"github.com/rackerlabs/understack/go/understackctl/helpers"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/envutil"
	"github.com/gookit/goutil/fsutil"

	"github.com/spf13/cobra"
)

//go:embed templates/clusterIssuer.tmpl
var clusterIssuerTemplate string

func NewCmdCertManagerSecret() *cobra.Command {
	return &cobra.Command{
		Use:   "certmanager-secrets",
		Short: "Generate certmanager-secrets secrets",
		Long:  "",
		Run:   certManagerGen,
	}
}

func certManagerGen(cmd *cobra.Command, args []string) {
	err := clusterIssuer()
	if err != nil {
		log.Error("certManagerGen failed", "error", err)
	}
}

// credGen prints out the cli version number
func clusterIssuer() error {
	vars := map[string]any{
		"UC_DEPLOY_EMAIL": envutil.Getenv("UC_DEPLOY_EMAIL"),
		"DNS_ZONE":        envutil.Getenv("DNS_ZONE"),
	}

	result, err := helpers.TemplateHelper(string(clusterIssuerTemplate), vars)
	if err != nil {
		return fmt.Errorf("template rendering failed: %w", err)
	}

	outputFilePath := helpers.GetManifestPathToService("cert-manager") + "/cluster-issuer.yaml"

	if err := fsutil.WriteFile(outputFilePath, result, os.ModePerm); err != nil {
		log.Fatal("error in kustomization.yaml file", "err", err)
		os.Exit(1)
	}
	helpers.UpdateKustomizeFile(helpers.GetManifestPathToService("cert-manager"))

	return nil
}
