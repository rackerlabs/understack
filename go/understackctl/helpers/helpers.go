package helpers

import (
	"path/filepath"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/envutil"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/yaml"
)

// SecretConfig holds configuration for creating secrets
type SecretConfig struct {
	Name      string
	Namespace string
	Data      map[string]string
}

func GetManifestPathToService(service string) string {
	return filepath.Join(
		envutil.Getenv("DEPLOY_NAME"),
		service,
	)
}

func CreateKubeSealSecretFile(config SecretConfig, filePath string) error {
	secret := &corev1.Secret{
		TypeMeta: metav1.TypeMeta{
			Kind:       "Secret",
			APIVersion: "v1",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name:      config.Name,
			Namespace: config.Namespace,
		},
		Type:       corev1.SecretTypeOpaque,
		StringData: config.Data,
	}

	secretYAML, err := yaml.Marshal(secret)
	if err != nil {
		return err
	}

	log.Info("creating kubeseal secret", "path", filePath)
	return KubeSeal(secretYAML, filePath)
}
