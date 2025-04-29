package controller

import (
	"context"
	"fmt"

	dexv1alpha1 "github.com/rackerlabs/understack/go/dexop/api/v1alpha1"
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

	if value, ok := secret.Data["client-secret"]; ok {
		return string(value), nil
	}
	return "", fmt.Errorf("client-secret key not found")
}

func (s SecretManager) writeSecret(r *ClientReconciler, ctx context.Context, clientSpec *dexv1alpha1.Client, value string) (*v1.Secret, error) {
	secret := &v1.Secret{
		TypeMeta: metav1.TypeMeta{},
		ObjectMeta: metav1.ObjectMeta{
			Name:      clientSpec.Spec.SecretName,
			Namespace: clientSpec.Spec.SecretNamespace,
		},
		Data: map[string][]byte{"client-secret": []byte(value), "issuer": []byte(clientSpec.Spec.Issuer), "client-id": []byte(clientSpec.Spec.Name)},
		Type: "Opaque",
	}

	err := r.Create(ctx, secret)
	if err != nil {
		return nil, err
	}
	return secret, nil
}

func (s SecretManager) generateSecret(r *ClientReconciler, ctx context.Context, clientSpec *dexv1alpha1.Client) (*v1.Secret, error) {
	res, err := password.Generate(48, 10, 10, false, false)
	if err != nil {
		return nil, err
	}
	return s.writeSecret(r, ctx, clientSpec, res)
}
