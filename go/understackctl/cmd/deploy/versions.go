package deploy

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"text/tabwriter"

	"github.com/spf13/cobra"
)

func newCmdDeployVersions() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "versions",
		Short: "Show the UnderStack version deployed in each environment",
		Long:  `List every environment in the deployment repo along with its understack_ref and deploy_ref from deploy.yaml.`,
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			return runDeployVersions(".", cmd.OutOrStdout())
		},
	}

	return cmd
}

func runDeployVersions(repoDir string, out io.Writer) error {
	entries, err := os.ReadDir(repoDir)
	if err != nil {
		return fmt.Errorf("failed to read deployment repo: %w", err)
	}

	// tabwriter defers write errors to Flush, which is returned below.
	w := tabwriter.NewWriter(out, 0, 4, 2, ' ', 0)
	_, _ = fmt.Fprintln(w, "ENVIRONMENT\tUNDERSTACK\tDEPLOY")

	found := false
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		clusterDir := filepath.Join(repoDir, entry.Name())
		if _, err := os.Stat(filepath.Join(clusterDir, "deploy.yaml")); err != nil {
			continue
		}

		config, err := loadDeployConfig(clusterDir)
		if err != nil {
			return err
		}

		understackRef, _ := config["understack_ref"].(string)
		if understackRef == "" {
			understackRef = "unknown"
		}

		deployRef, _ := config["deploy_ref"].(string)
		if deployRef == "" {
			deployRef = "unknown"
		}

		_, _ = fmt.Fprintf(w, "%s\t%s\t%s\n", entry.Name(), understackRef, deployRef)
		found = true
	}

	if !found {
		return fmt.Errorf("no environments with a deploy.yaml found, is this a deployment repo?")
	}

	return w.Flush()
}
