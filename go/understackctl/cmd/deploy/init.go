package deploy

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/log"
	"github.com/rackerlabs/understack/go/understackctl/internal/chartvalues"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

const understackRepoURL = "https://github.com/rackerlabs/understack.git"

func newCmdDeployInit() *cobra.Command {
	var clusterType string
	var gitRemote string

	cmd := &cobra.Command{
		Use:   "init <cluster-name>",
		Short: "Create cluster directory with deploy.yaml",
		Long: `Initialize a cluster directory with deploy.yaml configuration.
Populates global and site component sections based on cluster type.`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			clusterName := args[0]
			return runDeployInit(clusterName, clusterType, gitRemote)
		},
	}

	cmd.Flags().StringVar(&clusterType, "type", "aio", "Cluster type: global, site, or aio")
	cmd.Flags().StringVar(&gitRemote, "git-remote", "origin", "Git remote name to use for deploy URL")

	return cmd
}

func runDeployInit(clusterName, clusterType, gitRemote string) error {
	if clusterType != "global" && clusterType != "site" && clusterType != "aio" {
		return fmt.Errorf("invalid cluster type %q: must be global, site, or aio", clusterType)
	}

	clusterDir := clusterName
	if err := os.MkdirAll(clusterDir, 0755); err != nil {
		return fmt.Errorf("failed to create cluster directory: %w", err)
	}

	deployYamlPath := filepath.Join(clusterDir, "deploy.yaml")
	if _, err := os.Stat(deployYamlPath); err == nil {
		return fmt.Errorf("deploy.yaml already exists at %s", deployYamlPath)
	}

	deployURL, err := getGitRemoteURL(gitRemote)
	if err != nil {
		log.Warnf("Could not detect git remote: %v", err)
		deployURL = ""
	}

	config := make(map[string]any)
	config["understack_url"] = understackRepoURL
	config["deploy_url"] = deployURL

	log.Infof("Fetching component list from UnderStack")
	valuesData, err := chartvalues.FetchValues("main")
	if err != nil {
		return fmt.Errorf("failed to fetch values.yaml: %w", err)
	}

	globalComponents, siteComponents, err := chartvalues.ParseComponents(valuesData)
	if err != nil {
		return fmt.Errorf("failed to parse components: %w", err)
	}

	if clusterType == "global" || clusterType == "aio" {
		globalMap := make(map[string]any)
		globalMap["enabled"] = true
		for _, c := range globalComponents {
			globalMap[c.Key] = map[string]any{"enabled": true}
		}
		config["global"] = globalMap
	}

	if clusterType == "site" || clusterType == "aio" {
		siteMap := make(map[string]any)
		siteMap["enabled"] = true
		for _, c := range siteComponents {
			siteMap[c.Key] = map[string]any{"enabled": true}
		}
		config["site"] = siteMap
	}

	data, err := yaml.Marshal(&config)
	if err != nil {
		return fmt.Errorf("failed to marshal config: %w", err)
	}

	if err := os.WriteFile(deployYamlPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write deploy.yaml: %w", err)
	}

	log.Infof("Created %s", deployYamlPath)
	return nil
}

func getGitRemoteURL(remoteName string) (string, error) {
	cmd := exec.Command("git", "remote", "get-url", remoteName)
	output, err := cmd.Output()
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(output)), nil
}
