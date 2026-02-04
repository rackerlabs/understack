package deploy

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/log"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

const (
	deployRepoEnvVar = "UC_DEPLOY"
	deployRepoFlag   = "deploy-repo"
)

// NewCmdDeploy returns the root "deploy" command for UnderStack deployments.
func NewCmdDeploy() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "deploy [--deploy-repo UC_DEPLOY] command",
		Short: "UnderStack deployment",
		RunE: func(cmd *cobra.Command, args []string) error {
			// Show help if no subcommands are provided
			return cmd.Help()
		},
		PersistentPreRunE: ensureDeployRepo,
	}

	addDeployRepoFlag(cmd)

	cmd.AddCommand(newCmdDeployInit())
	cmd.AddCommand(newCmdDeployCheck())
	cmd.AddCommand(newCmdDeployUpdate())
	cmd.AddCommand(newCmdDeployRender())

	return cmd
}

// addDeployRepoFlag binds and configures the persistent --deploy-repo flag.
func addDeployRepoFlag(cmd *cobra.Command) {
	// Bind environment variable
	if err := viper.BindEnv(deployRepoFlag, deployRepoEnvVar); err != nil {
		log.Fatal("failed to bind env var", "env", deployRepoEnvVar, "err", err)
		os.Exit(1)
	}

	// Set default value from env or fallback
	defaultRepo := viper.GetString(deployRepoFlag)
	if defaultRepo == "" {
		defaultRepo = "."
	}

	help := fmt.Sprintf("Path to your deployment repo (env: %s) (current: %s)", deployRepoEnvVar, defaultRepo)
	cmd.PersistentFlags().String(deployRepoFlag, "", help)

	if err := viper.BindPFlag(deployRepoFlag, cmd.PersistentFlags().Lookup(deployRepoFlag)); err != nil {
		log.Fatal("failed to bind flag", "flag", deployRepoFlag, "err", err)
		os.Exit(1)
	}
}

// ensureDeployRepo validates and switches to the deployment repo directory, if provided.
func ensureDeployRepo(cmd *cobra.Command, args []string) error {
	repoPath := viper.GetString(deployRepoFlag)
	if repoPath == "" {
		return nil // nothing to do
	}

	expandedPath, err := expandHomePath(repoPath)
	if err != nil {
		return fmt.Errorf("failed to expand path: %w", err)
	}

	info, err := os.Stat(expandedPath)
	if err != nil {
		return fmt.Errorf("could not access directory '%s': %w", expandedPath, err)
	}
	if !info.IsDir() {
		return fmt.Errorf("path '%s' is not a directory", expandedPath)
	}

	if err := os.Chdir(expandedPath); err != nil {
		return fmt.Errorf("failed to change working directory to '%s': %w", expandedPath, err)
	}

	log.Infof("Using deployment repo: %s", expandedPath)
	return nil
}

// expandHomePath expands a path starting with "~" to the user's home directory.
func expandHomePath(path string) (string, error) {
	if strings.HasPrefix(path, "~") {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		return filepath.Join(home, path[1:]), nil
	}
	return path, nil
}
