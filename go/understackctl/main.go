package main

import (
	"os"

	"github.com/rackerlabs/understack/go/understackctl/cmd/root"
)

func main() {
	err := root.Execute()
	if err != nil {
		os.Exit(1)
	}
}
