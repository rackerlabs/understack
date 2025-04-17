package ironic

import (
	"fmt"

	"github.com/rackerlabs/understack/go/deploy-cli/cmd"
	"github.com/rackerlabs/understack/go/deploy-cli/cmd/argocd"
	"github.com/rackerlabs/understack/go/deploy-cli/cmd/certManager"
	"github.com/rackerlabs/understack/go/deploy-cli/cmd/dex"
	"github.com/rackerlabs/understack/go/deploy-cli/cmd/helmConfig"
	"github.com/rackerlabs/understack/go/deploy-cli/cmd/node"
	"github.com/rackerlabs/understack/go/deploy-cli/cmd/openstack"
	"github.com/rackerlabs/understack/go/deploy-cli/cmd/other"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/envutil"
	"github.com/spf13/cobra"
)

func init() {
	cmd.RootCmd.AddCommand(All)
}

var All = &cobra.Command{
	Use:   "all",
	Short: "run all the steps required",
	Long:  "run all the steps required",
	Run:   all,
}

func all(cmd *cobra.Command, args []string) {

	log.Info("using envs",
		"UC_DEPLOY", envutil.Getenv("UC_DEPLOY"),
		"DEPLOY_NAME", envutil.Getenv("DEPLOY_NAME"),
		"UC_DEPLOY_GIT_URL", envutil.Getenv("UC_DEPLOY_GIT_URL"),
		"UC_DEPLOY_SSH_FILE", envutil.Getenv("UC_DEPLOY_SSH_FILE"),
		"DNS_ZONE", envutil.Getenv("DNS_ZONE"),
		"UC_DEPLOY_EMAIL", envutil.Getenv("UC_DEPLOY_EMAIL"),
		"UC_AIO", envutil.Getenv("UC_AIO"),
	)

	fmt.Println(envutil.Getenv("UC_DEPLOY"))
	fmt.Println(envutil.Getenv("DEPLOY_NAME"))

	log.Info("== Node Update")
	node.Node.Run(cmd, args)

	log.Info("== Node ArgoCd")
	argocd.ArgoCMD.Run(cmd, args)

	log.Info("== Node Cert Manager")
	certManager.CertManager.Run(cmd, args)

	log.Info("== Running Dex")
	dex.Dex.Run(cmd, args)

	log.Info("== Running For Other Services")
	other.Other.Run(cmd, args)

	log.Info("== Running Openstack")
	openstack.Openstack.Run(cmd, args)

	log.Info("== Creating Helm Configs")
	helmConfig.HelmConfig.Run(cmd, args)
}
