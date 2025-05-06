package quickstart

import (
	"fmt"
	"os"
	"os/exec"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/envutil"
	"github.com/rackerlabs/understack/go/understackctl/cmd/argocd"
	"github.com/rackerlabs/understack/go/understackctl/cmd/certManager"
	"github.com/rackerlabs/understack/go/understackctl/cmd/dex"
	"github.com/rackerlabs/understack/go/understackctl/cmd/helmConfig"
	"github.com/rackerlabs/understack/go/understackctl/cmd/node"
	"github.com/rackerlabs/understack/go/understackctl/cmd/openstack"
	"github.com/rackerlabs/understack/go/understackctl/cmd/other"
	"github.com/spf13/cobra"
)

func NewCmdQuickStart() *cobra.Command {
	return &cobra.Command{
		Use:   "quickstart",
		Short: "Run all the steps required",
		Long:  "Run all the steps required",
		Run:   qsRun,
	}
}

func qsRun(cmd *cobra.Command, args []string) {

	log.Info("using envs",
		"DEPLOY_NAME", envutil.Getenv("DEPLOY_NAME"),
		"UC_DEPLOY_GIT_URL", envutil.Getenv("UC_DEPLOY_GIT_URL"),
		"UC_DEPLOY_SSH_FILE", envutil.Getenv("UC_DEPLOY_SSH_FILE"),
		"DNS_ZONE", envutil.Getenv("DNS_ZONE"),
		"UC_DEPLOY_EMAIL", envutil.Getenv("UC_DEPLOY_EMAIL"),
		"UC_AIO", envutil.Getenv("UC_AIO"),
	)

	var errors []string

	// Check if kubeseal is installed
	_, err := exec.LookPath("kubeseal")
	if err != nil {
		errors = append(errors, "kubeseal is not installed on system, please install kubeseal binary")
	}

	// If there are any errors, report them all and exit
	if len(errors) > 0 {
		for _, errMsg := range errors {
			log.Warn(errMsg)
		}
		os.Exit(1)
	}

	fmt.Println(envutil.Getenv("DEPLOY_NAME"))

	log.Info("== Node Update")
	node.NewCmdNode().Run(cmd, args)

	log.Info("== Node ArgoCd")
	argocd.NewCmdArgocdSecret().Run(cmd, args)

	log.Info("== Node Cert Manager")
	certManager.NewCmdCertManagerSecret().Run(cmd, args)

	log.Info("== Running Dex")
	dex.NewCmdDexSecrets().Run(cmd, args)

	log.Info("== Running For Other Services")
	other.NewCmdOtherSecrets().Run(cmd, args)

	log.Info("== Running Openstack")
	openstack.NewCmdOpenstackSecrets().Run(cmd, args)

	log.Info("== Creating Helm Configs")
	helmConfig.NewCmdHelmConfig().Run(cmd, args)
}
