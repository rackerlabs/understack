package controller

import (
	"context"
	"fmt"

	"github.com/sethvargo/go-password/password"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

type SecretManager struct {
}

func (s SecretManager) readSecret(r *ClientReconciler, ctx context.Context, name, namespace string) (string, error) {
	secret := &v1.Secret{}

	err := r.Get(ctx, client.ObjectKey{Name: name, Namespace: namespace}, secret)
	if err != nil {
		return "", err
	}

	if value, ok := secret.Data["secret"]; ok {
		return string(value), nil
	}
	return "", fmt.Errorf("secret key not found")
}

func (s SecretManager) writeSecret(r *ClientReconciler, ctx context.Context, name, namespace, value string) (*v1.Secret, error) {
	secret := &v1.Secret{
		TypeMeta: metav1.TypeMeta{},
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
		},
		Data: map[string][]byte{"secret": []byte(value)},
		Type: "Opaque",
	}

	err := r.Create(ctx, secret)
	if err != nil {
		return nil, err
	}
	return secret, nil
}

func (s SecretManager) generateSecret(r *ClientReconciler, ctx context.Context, name, namespace string) (*v1.Secret, error) {
	res, err := password.Generate(48, 10, 10, false, false)
	if err != nil {
		return nil, err
	}
	return s.writeSecret(r, ctx, name, namespace, res)
}
