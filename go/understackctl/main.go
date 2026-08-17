package main

import (
	"os"

	"github.com/rackerlabs/understack/go/understackctl/cmd/root"
)

// Populated at build time by the -X linker flags set in the Makefile.
var (
	version = "dev"
	commit  = "unknown"
)

func main() {
	root.SetVersion(version, commit)

	err := root.Execute()
	if err != nil {
		os.Exit(1)
	}
}
