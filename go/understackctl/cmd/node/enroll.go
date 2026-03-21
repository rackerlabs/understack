package node

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"strings"

	"github.com/spf13/cobra"
	"k8s.io/client-go/tools/clientcmd"
)

const (
	enrollWorkflowNamespace = "argo-events"
	enrollWorkflowTemplate  = "wftmpl/enroll-server"
)

type enrollOptions struct {
	OldPassword    string
	FirmwareUpdate bool
	RaidConfigure  bool
	ExternalCMDBID string
	Logs           bool
}

func newCmdEnrollServer() *cobra.Command {
	opts := &enrollOptions{}

	cmd := &cobra.Command{
		Use:          "enroll-server <ip-address>",
		Short:        "Submit the enroll-server Argo workflow for a node",
		Args:         cobra.ExactArgs(1),
		SilenceUsage: true,
		RunE: func(cmd *cobra.Command, args []string) error {
			ipAddress := args[0]
			if net.ParseIP(ipAddress) == nil {
				return fmt.Errorf("invalid IP address: %s", ipAddress)
			}

			argoArgs, err := buildEnrollArgoArgs(cmd, ipAddress, opts)
			if err != nil {
				return err
			}

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
				return fmt.Errorf("run argo enroll workflow: %w", err)
			}

			return nil
		},
	}

	cmd.Flags().StringVar(&opts.OldPassword, "old-password", "", "Existing node password")
	cmd.Flags().BoolVar(&opts.FirmwareUpdate, "firmware-update", false, "Whether to perform a firmware update")
	cmd.Flags().BoolVar(&opts.RaidConfigure, "raid-configure", false, "Whether to configure RAID")
	cmd.Flags().StringVar(&opts.ExternalCMDBID, "external-cmdb-id", "", "External CMDB identifier")
	cmd.Flags().BoolVar(&opts.Logs, "log", false, "Stream workflow logs after submission")

	return cmd
}

func buildEnrollArgoArgs(cmd *cobra.Command, ipAddress string, opts *enrollOptions) ([]string, error) {
	args := []string{
		"-n", enrollWorkflowNamespace,
		"submit",
		"--from", enrollWorkflowTemplate,
		"-p", fmt.Sprintf("ip_address=%s", ipAddress),
	}

	if opts.Logs {
		args = append(args, "--log")
	}

	if cmd.Flags().Changed("old-password") {
		args = append(args, "-p", fmt.Sprintf("old_password=%s", opts.OldPassword))
	}

	if cmd.Flags().Changed("firmware-update") {
		args = append(args, "-p", fmt.Sprintf("firmware_update=%t", opts.FirmwareUpdate))
	}

	if cmd.Flags().Changed("raid-configure") {
		args = append(args, "-p", fmt.Sprintf("raid_configure=%t", opts.RaidConfigure))
	}

	if cmd.Flags().Changed("external-cmdb-id") {
		args = append(args, "-p", fmt.Sprintf("external_cmdb_id=%s", opts.ExternalCMDBID))
	}

	return args, nil
}

func currentKubeContext() (string, error) {
	config, err := clientcmd.NewDefaultPathOptions().GetStartingConfig()
	if err != nil {
		return "", err
	}

	if config.CurrentContext == "" {
		return "", fmt.Errorf("no current context is set")
	}

	return config.CurrentContext, nil
}

func shellQuoteCommand(name string, args []string) string {
	parts := make([]string, 0, len(args)+1)
	parts = append(parts, shellQuote(name))
	for _, arg := range args {
		parts = append(parts, shellQuote(arg))
	}

	return strings.Join(parts, " ")
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}

	if !strings.ContainsAny(value, " \t\n'\"\\$&;|<>(){}[]*?!#~=`") {
		return value
	}

	return "'" + strings.ReplaceAll(value, "'", `'\''`) + "'"
}
