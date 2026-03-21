package node

import (
	"fmt"
	"os"
	"os/exec"

	"github.com/spf13/cobra"
)

const inspectWorkflowTemplate = "wftmpl/inspect-server"

type inspectOptions struct {
	Logs bool
}

func newCmdInspectServer() *cobra.Command {
	opts := &inspectOptions{}

	cmd := &cobra.Command{
		Use:          "inspect-server <node-id>",
		Short:        "Submit the inspect-server Argo workflow for a node",
		Args:         cobra.ExactArgs(1),
		SilenceUsage: true,
		RunE: func(cmd *cobra.Command, args []string) error {
			nodeID := args[0]

			argoArgs := buildInspectArgoArgs(nodeID, opts)

			currentContext, err := currentKubeContext()
			if err != nil {
				return fmt.Errorf("get current Kubernetes context: %w", err)
			}

			cmd.Printf("Kubernetes context: %s\n", currentContext)
			cmd.Printf("Running: %s\n", shellQuoteCommand("argo", argoArgs))

			argoCmd := exec.Command("argo", argoArgs...)
			argoCmd.Stdin = os.Stdin
			argoCmd.Stdout = cmd.OutOrStdout()
			argoCmd.Stderr = cmd.ErrOrStderr()

			if err := argoCmd.Run(); err != nil {
				return fmt.Errorf("run argo inspect workflow: %w", err)
			}

			return nil
		},
	}

	cmd.Flags().BoolVar(&opts.Logs, "log", false, "Stream workflow logs after submission")

	return cmd
}

func buildInspectArgoArgs(nodeID string, opts *inspectOptions) []string {
	args := []string{
		"-n", enrollWorkflowNamespace,
		"submit",
		"--from", inspectWorkflowTemplate,
		"-p", fmt.Sprintf("node=%s", nodeID),
	}

	if opts.Logs {
		args = append(args, "--log")
	}

	return args
}
