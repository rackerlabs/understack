package cmd

import (
	"fmt"
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
	PreRun: func(cmd *cobra.Command, args []string) {
	},
	Run: func(cmd *cobra.Command, args []string) {
	},
	PostRun: func(cmd *cobra.Command, args []string) {
	},
	PersistentPostRun: func(cmd *cobra.Command, args []string) {
	},
}

// Execute will execute the root command
func Execute() error {
	return rootCmd.Execute()
}
