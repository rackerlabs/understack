package node

import "github.com/spf13/cobra"

func NewCmdNode() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "node",
		Short: "Manage node lifecycle workflows",
		Long:  "Manage node lifecycle workflows by wrapping Argo workflows and related platform APIs",
	}

	cmd.AddCommand(newCmdEnrollServer())
	cmd.AddCommand(newCmdInspectServer())

	return cmd
}
