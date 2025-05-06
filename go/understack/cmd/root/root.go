package root

import (
	"fmt"

	"github.com/rackerlabs/understack/go/understack/cmd/argocd"
	"github.com/rackerlabs/understack/go/understack/cmd/certManager"
	"github.com/rackerlabs/understack/go/understack/cmd/dex"
	"github.com/rackerlabs/understack/go/understack/cmd/helmConfig"
	"github.com/rackerlabs/understack/go/understack/cmd/node"
	"github.com/rackerlabs/understack/go/understack/cmd/openstack"
	"github.com/rackerlabs/understack/go/understack/cmd/other"
	"github.com/rackerlabs/understack/go/understack/cmd/quickstart"
	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "understack SUBCOMMAND ...",
	Short: "UnderStack CLI",
	Long:  ``,
	RunE: func(cmd *cobra.Command, args []string) error {
		// If no subcommand, show help
		return fmt.Errorf("a subcommand is required")
	},
}

func init() {
	rootCmd.AddCommand(argocd.NewCmdArgocdSecret())
	rootCmd.AddCommand(certManager.NewCmdCertManagerSecret())
	rootCmd.AddCommand(dex.NewCmdDexSecrets())
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
