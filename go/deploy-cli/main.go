package main

import (
	"github.com/rackerlabs/understack/go/deploy-cli/cmd"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/all"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/argocd"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/certManager"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/dex"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/helmConfig"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/node"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/openstack"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/other"

	"os"
	"os/exec"

	"github.com/charmbracelet/log"
)

func main() {
	var errors []string

	// Check for DNS_ZONE environment variable
	if os.Getenv("DNS_ZONE") == "" {
		errors = append(errors, "DNS_ZONE env not set for shell")
	}

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

	cmd.Execute()
}
