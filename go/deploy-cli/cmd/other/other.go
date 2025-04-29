package other

import (
	"os"
	"path/filepath"

	"github.com/rackerlabs/understack/go/deploy-cli/cmd"
	"github.com/rackerlabs/understack/go/deploy-cli/helpers"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/envutil"
	"github.com/gookit/goutil/fsutil"
	"github.com/gookit/goutil/strutil"

	"context"
	"fmt"

	"github.com/spf13/cobra"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func init() {
	cmd.RootCmd.AddCommand(Other)
}

var openStackSecrets map[string]any

var Other = &cobra.Command{
	Use:   "other-secrets",
	Short: "Create secret for keystone, ironic, placement, neutron, nova, glance",
	Long:  "Create secret for keystone, ironic, placement, neutron, nova, glance",
	Run:   generateOtherSecrets,
}

func generateOtherSecrets(_ *cobra.Command, _ []string) {
	// create constant OpenStack memcache key to avoid cache invalidation on deploy
	openStackSecrets = map[string]any{
		"DNS_ZONE":                envutil.Getenv("DNS_ZONE"),
		"MEMCACHE_SECRET_KEY":     helpers.GenerateRandomString(32),
		"HORIZON_DB_PASSWORD":     helpers.GenerateRandomString(32),
		"KEYSTONE_ADMIN_PASSWORD": loadOrGenSecret("admin-keystone-password", "openstack"),
	}

	services := []string{"keystone", "ironic", "placement", "neutron", "nova", "glance", "horizon"}
	dependencies := []string{"rabbitmq", "keystone", "db"}

	for _, service := range services {
		log.Warnf("Running For %s Services", service)

		if err := generateServiceSecrets(service, dependencies); err != nil {
			log.Errorf("Failed to generate secrets for %s: %v", service, err)
		}
	}

	if err := updateOpenStackSecretsFile(); err != nil {
		log.Fatal("failed to update openstack file", "err", err)
	}

	// Create Empty Dirs
	emptyDirs := []string{"argo-events", "ovn", "metallb", "undersync", "cilium"}
	for _, service := range emptyDirs {
    if err := fsutil.WriteFile(helpers.GetManifestPathToService(service)+"/.keep", "", os.ModePerm); err != nil {
      log.Errorf("Failed creating .keep file for %s: %v", service, err)
    }
	}
}

func generateServiceSecrets(service string, dependencies []string) error {
	manifestPath := helpers.GetManifestPathToService(service)

	for _, dep := range dependencies {
		secretName := fmt.Sprintf("secret-%s-password", dep)
		filePath := filepath.Join(manifestPath, secretName+".yaml")
		secret := loadOrGenSecret(fmt.Sprintf("%s-%s-password", service, dep), "openstack")

		config := helpers.SecretConfig{
			Name:      secretName,
			Namespace: "openstack",
			Data: map[string]string{
				"username": service,
				"password": secret,
			},
		}

		if err := helpers.CreateKubeSealSecretFile(config, filePath); err != nil {
			return err
		}
		// add all the passwords to map, for openstack secrets.yaml file
		openStackSecrets[strutil.Uppercase(fmt.Sprintf("%s_%s_PASSWORD", service, dep))] = secret
	}

	helpers.UpdateKustomizeFile(manifestPath)

	return nil
}

func updateOpenStackSecretsFile() error {
	data, err := helpers.TemplateHelper(SecretOpenStackTemplate, openStackSecrets)
	if err != nil {
		return fmt.Errorf("failed to render template: %w", err)
	}

	secretFilePath := filepath.Join(
		envutil.Getenv("UC_DEPLOY"),
		envutil.Getenv("DEPLOY_NAME"),
		"manifests",
		"secret-openstack.yaml",
	)
	log.Info("updating secret-openstack.yaml", "path", secretFilePath)

	if err := fsutil.WriteFile(secretFilePath, data, os.ModePerm); err != nil {
		return fmt.Errorf("failed to write %s: %w", secretFilePath, err)
	}
	return nil
}

func loadOrGenSecret(serviceName, namespace string) string {
	client, _ := helpers.KubeClientSet().CoreV1().Secrets(namespace).Get(context.Background(), serviceName, metav1.GetOptions{})
	encodedPassword, ok := client.Data["password"]
	if ok {
		log.Info("using password from cluster", "service", serviceName, "namespace", namespace)
		return string(encodedPassword)
	}
	log.Warn("password not in cluster", "service", serviceName, "namespace", namespace)
	log.Info("Creating Random password for", "service", serviceName, "namespace", namespace)
	return helpers.GenerateRandomString(32)
}
