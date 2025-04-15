package openstack

import (
	"github.com/rackerlabs/understack/go/deploy-cli/cmd"
	"github.com/rackerlabs/understack/go/deploy-cli/helpers"

	"github.com/charmbracelet/log"

	"github.com/spf13/cobra"
)

func init() {
	cmd.RootCmd.AddCommand(Openstack)
}

var Openstack = &cobra.Command{
	Use:   "openstack-secrets",
	Short: "Generate openstack-secrets",
	Long:  "Generate openstack-secrets",
	Run:   openStackGen,
}

func openStackGen(cmd *cobra.Command, args []string) {
	if err := generateMariaDBSecret(); err != nil {
		log.Errorf("Failed to generate MariaDB secret: %v", err)
	}
}

// credGen prints out the cli version number
func generateMariaDBSecret() error {
	filePath := helpers.GetManifestPathToService("openstack") + "/secret-mariadb.yaml"

	config := helpers.SecretConfig{
		Name:      "mariadb",
		Namespace: "openstack",
		Data: map[string]string{
			"password":      helpers.GenerateRandomString(32),
			"root-password": helpers.GenerateRandomString(32),
		},
	}

	if err := helpers.CreateKubeSealSecretFile(config, filePath); err != nil {
		log.Warn("Failed to create sealed secret", "error", err)
		return err
	}

	helpers.UpdateKustomizeFile(helpers.GetManifestPathToService("openstack"))

	return nil
}
