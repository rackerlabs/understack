package cmd

import (
	"github.com/spf13/cobra"
)

var RootCmd = &cobra.Command{
	Use:   "understack",
	Short: "",
	Long:  ``,
	RunE: func(cmd *cobra.Command, args []string) error {
		// If no subcommand, show help
		return cmd.Help()
	},
	PersistentPreRun: func(cmd *cobra.Command, args []string) {
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
	return RootCmd.Execute()
}

func init() {
}
