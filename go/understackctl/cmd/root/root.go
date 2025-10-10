package root

import (
	"fmt"

	"github.com/rackerlabs/understack/go/understackctl/cmd/argocd"
	"github.com/rackerlabs/understack/go/understackctl/cmd/certManager"
	"github.com/rackerlabs/understack/go/understackctl/cmd/deploy"
	"github.com/rackerlabs/understack/go/understackctl/cmd/deviceType"
	"github.com/rackerlabs/understack/go/understackctl/cmd/dex"
	"github.com/rackerlabs/understack/go/understackctl/cmd/flavor"
	"github.com/rackerlabs/understack/go/understackctl/cmd/helmConfig"
	"github.com/rackerlabs/understack/go/understackctl/cmd/node"
	"github.com/rackerlabs/understack/go/understackctl/cmd/openstack"
	"github.com/rackerlabs/understack/go/understackctl/cmd/other"
	"github.com/rackerlabs/understack/go/understackctl/cmd/quickstart"
	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "understackctl SUBCOMMAND ...",
	Short: "UnderStack CLI",
	Long:  ``,
	RunE: func(cmd *cobra.Command, args []string) error {
		// If no subcommand, show help
		return fmt.Errorf("a subcommand is required")
	},
}

func init() {
	rootCmd.AddCommand(deploy.NewCmdDeploy())
	rootCmd.AddCommand(argocd.NewCmdArgocdSecret())
	rootCmd.AddCommand(certManager.NewCmdCertManagerSecret())
	rootCmd.AddCommand(deviceType.NewCmdDeviceType())
	rootCmd.AddCommand(dex.NewCmdDexSecrets())
	rootCmd.AddCommand(flavor.NewCmdFlavor())
	rootCmd.AddCommand(helmConfig.NewCmdHelmConfig())
	rootCmd.AddCommand(node.NewCmdNode())
	rootCmd.AddCommand(openstack.NewCmdOpenstackSecrets())
	rootCmd.AddCommand(quickstart.NewCmdQuickStart())
	rootCmd.AddCommand(other.NewCmdOtherSecrets())
}

// Execute will execute the root command
func Execute() error {
	return rootCmd.Execute()
}
