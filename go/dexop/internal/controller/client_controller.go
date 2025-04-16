/*
Copyright 2025.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package controller

import (
	"context"
	"fmt"
	"strings"

	"github.com/go-logr/logr"
	dexv1alpha1 "github.com/rackerlabs/understack/go/dexop/api/v1alpha1"
	dexmgr "github.com/rackerlabs/understack/go/dexop/dex"
	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"
)

const dexFinalizer = "dex.rax.io/finalizer"

// ClientReconciler reconciles a Client object
type ClientReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=dex.rax.io,resources=clients,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=dex.rax.io,resources=clients/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=dex.rax.io,resources=clients/finalizers,verbs=update

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
// TODO(user): Modify the Reconcile function to compare the state specified by
// the Client object against the actual cluster state, and then
// perform operations to make the cluster state reflect the state specified by
// the user.
//
// For more details, check Reconcile and its Result here:
// - https://pkg.go.dev/sigs.k8s.io/controller-runtime@v0.19.0/pkg/reconcile
func (r *ClientReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	_ = log.FromContext(ctx)
	reqLogger := ctrl.Log.WithValues("client", req.NamespacedName)

	mgr, err := dexmgr.NewDexManager("127.0.0.1:5557", "./grpc_ca.crt", "./grpc_client.key", "./grpc_client.crt")
	if err != nil {
		ctrl.Log.Error(err, "While getting the DexManager")
		return ctrl.Result{}, err
	}

	clientSpec := &dexv1alpha1.Client{}
	if err := r.Get(ctx, req.NamespacedName, clientSpec); err != nil {
		if errors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	reqLogger.Info("reconciling Client")

	// delete if no longer needed
	deleteRequested := clientSpec.GetDeletionTimestamp() != nil
	if deleteRequested {
		if controllerutil.ContainsFinalizer(clientSpec, dexFinalizer) {
			if err := r.finalizeDeletion(reqLogger, clientSpec, mgr); err != nil {
				return ctrl.Result{}, err
			}

			// remove finalizer
			controllerutil.RemoveFinalizer(clientSpec, dexFinalizer)
			err := r.Update(ctx, clientSpec)
			if err != nil {
				return ctrl.Result{}, err
			}
		}
		return ctrl.Result{}, nil
	}

	// add finalizer
	if !controllerutil.ContainsFinalizer(clientSpec, dexFinalizer) {
		controllerutil.AddFinalizer(clientSpec, dexFinalizer)
		err := r.Update(ctx, clientSpec)
		if err != nil {
			return ctrl.Result{}, err
		}
	}

	// if secretName specified, read the secret
	if clientSpec.Spec.SecretName != "" {
		if clientSpec.Spec.SecretNamespace == "" {
			clientSpec.Spec.SecretNamespace = req.NamespacedName.Namespace
		}
		// read existing or generate a secret
		value, err := r.readSecret(ctx, clientSpec.Spec.SecretName, clientSpec.Spec.SecretNamespace)
		if err != nil {
			if errors.IsNotFound(err) && clientSpec.Spec.GenerateSecret {
				secret, err := r.writeSecret(ctx, clientSpec.Spec.SecretName, clientSpec.Spec.SecretNamespace, "ABRACADAXRA")
				if err != nil {
					reqLogger.Error(err, "Unable to write secret", "secretName", clientSpec.Spec.SecretName)
					return ctrl.Result{}, err
				}

				if secret.Data["secret"] == nil {
					reqLogger.Error(nil, "Secret data is missing", "SecretName", clientSpec.Spec.SecretName)
				}
				value = string(secret.Data["secret"])
				ctrl.SetControllerReference(clientSpec, secret, r.Scheme)
				if err = r.Update(ctx, secret); err != nil {
					return ctrl.Result{}, err
				}
			} else {
				reqLogger.Error(err, "Unable to read secret", "secretName", clientSpec.Spec.SecretName)
				return ctrl.Result{}, err
			}
		}
		clientSpec.Spec.SecretValue = value
	}

	existing, err := mgr.GetOauth2Client(clientSpec.Spec.Name)
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "not found") {
			ctrl.Log.Info("Client does not exist in Dex. Creating one.", "name", clientSpec.Spec.Name)
			if _, err = mgr.CreateOauth2Client(clientSpec); err != nil {
				reqLogger.Error(err, "Unable to create client in dex")
				return ctrl.Result{}, err
			}
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// update
	if existing != nil {
		reqLogger.Info("making an UpdateOauth2Client call")
		mgr.UpdateOauth2Client(clientSpec)
	}
	return ctrl.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *ClientReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&dexv1alpha1.Client{}).
		Complete(r)
}

func (r *ClientReconciler) finalizeDeletion(reqLogger logr.Logger, c *dexv1alpha1.Client, mgr *dexmgr.DexManager) error {
	reqLogger.Info("Client is being removed")
	if _, err := mgr.RemoveOauth2Client(c.Spec.Name); err != nil {
		return err
	}
	return nil
}

func (r *ClientReconciler) readSecret(ctx context.Context, name, namespace string) (string, error) {
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

func (r *ClientReconciler) writeSecret(ctx context.Context, name, namespace, value string) (*v1.Secret, error) {
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
