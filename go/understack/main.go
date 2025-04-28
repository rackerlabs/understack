package main

import (
	"os"

	"github.com/rackerlabs/understack/go/understack/cmd"
	_ "github.com/rackerlabs/understack/go/understack/cmd/argocd"
	_ "github.com/rackerlabs/understack/go/understack/cmd/certManager"
	_ "github.com/rackerlabs/understack/go/understack/cmd/dex"
	_ "github.com/rackerlabs/understack/go/understack/cmd/helmConfig"
	_ "github.com/rackerlabs/understack/go/understack/cmd/init"
	_ "github.com/rackerlabs/understack/go/understack/cmd/node"
	_ "github.com/rackerlabs/understack/go/understack/cmd/openstack"
	_ "github.com/rackerlabs/understack/go/understack/cmd/other"
)

func main() {
  err := cmd.Execute()
  if err != nil {
    os.Exit(1)
  }
}
