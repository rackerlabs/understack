package main

import (
	"os"

	"github.com/rackerlabs/understack/go/deploy-cli/cmd"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/argocd"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/certManager"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/dex"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/helmConfig"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/init"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/node"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/openstack"
	_ "github.com/rackerlabs/understack/go/deploy-cli/cmd/other"
)

func main() {
  err := cmd.Execute()
  if err != nil {
    os.Exit(1)
  }
}
