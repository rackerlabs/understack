package cmd

import (
	"fmt"
	"github.com/charmbracelet/log"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
	"os"
	"path/filepath"
	"strings"
)

const (
	deployRepoEnvVar = "UC_DEPLOY"
	deployRepoFlag   = "deploy-repo"
)

var DeployCmd = &cobra.Command{
	Use:   "deploy [--deploy-repo UC_DEPLOY] command",
	Short: "UnderStack deployment",
	Long:  ``,
	RunE: func(cmd *cobra.Command, args []string) error {
		// If no subcommand, show help
		return cmd.Help()
	},
	PersistentPreRunE: preRun,
	PreRun: func(cmd *cobra.Command, args []string) {
	},
	Run: func(cmd *cobra.Command, args []string) {
	},
	PostRun: func(cmd *cobra.Command, args []string) {
	},
	PersistentPostRun: func(cmd *cobra.Command, args []string) {
	},
}

func expandPath(path string) (string, error) {
	if strings.HasPrefix(path, "~") {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		return filepath.Join(home, path[1:]), nil
	}
	return path, nil
}

func preRun(cmd *cobra.Command, args []string) error {
	deployRepo := viper.GetString(deployRepoFlag)
	if deployRepo == "" {
		return nil
	}

	expandedRepoDir, err := expandPath(deployRepo)
	if err != nil {
		return fmt.Errorf("failed to expand path: %w", err)
	}

	info, err := os.Stat(expandedRepoDir)
	if err != nil {
		return fmt.Errorf("could not access directory '%s': %w", expandedRepoDir, err)
	}
	if !info.IsDir() {
		return fmt.Errorf("path '%s' is not a directory", expandedRepoDir)
	}

	// Switch working directory
	if err := os.Chdir(expandedRepoDir); err != nil {
		return fmt.Errorf("failed to change working directory to '%s': %w", expandedRepoDir, err)
	}

	log.Infof("deployment repo path: %s", expandedRepoDir)

	return nil
}

func init() {
	// bind our flag
	if err := viper.BindEnv(deployRepoFlag, deployRepoEnvVar); err != nil {
		log.Fatal("failed to bind", "env", deployRepoFlag, "err", err)
		os.Exit(1)
	}
	deployRepo := viper.GetString(deployRepoFlag)
	if deployRepo == "" {
		deployRepo = "."
	}
	helpText := fmt.Sprintf(
		"Path to your deployment repo (env: %s) (current: %s)",
		deployRepoEnvVar, deployRepo,
	)
	DeployCmd.PersistentFlags().String(deployRepoFlag, "", helpText)
	if err := viper.BindPFlag(deployRepoFlag, DeployCmd.PersistentFlags().Lookup(deployRepoFlag)); err != nil {
		log.Fatal("failed to bind", "flag", deployRepoFlag, "err", err)
		os.Exit(1)
	}

	rootCmd.AddCommand(DeployCmd)
}
