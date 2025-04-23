/*
Copyright 2025 Rackspace Technology.

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
	"strings"

	"github.com/go-logr/logr"
	dexv1alpha1 "github.com/rackerlabs/understack/go/dexop/api/v1alpha1"
	dexmgr "github.com/rackerlabs/understack/go/dexop/dex"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"
)

const dexFinalizer = "dex.rax.io/finalizer"

// ClientReconciler reconciles a Client object
type ClientReconciler struct {
	client.Client
	Scheme     *runtime.Scheme
	DexManager *dexmgr.DexManager
}

// +kubebuilder:rbac:groups=dex.rax.io,resources=clients,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=dex.rax.io,resources=clients/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=dex.rax.io,resources=clients/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch;update;patch

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
// For more details, check Reconcile and its Result here:
// - https://pkg.go.dev/sigs.k8s.io/controller-runtime@v0.19.0/pkg/reconcile
func (r *ClientReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	_ = log.FromContext(ctx)
	reqLogger := ctrl.Log.WithValues("client", req.NamespacedName)

	clientSpec, err := r.getClientSpec(ctx, req.NamespacedName)
	if err != nil {
		return ctrl.Result{}, err
	}

	// resource was deleted but it is being finalized
	if clientSpec == nil {
		return ctrl.Result{}, nil
	}

	reqLogger.Info("Reconciling Client")

	// delete if no longer needed
	deleteRequested := clientSpec.GetDeletionTimestamp() != nil
	if deleteRequested {
		if controllerutil.ContainsFinalizer(clientSpec, dexFinalizer) {
			if err := r.finalizeDeletion(reqLogger, clientSpec, r.DexManager); err != nil {
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
	secretmgr := new(SecretManager)
	if clientSpec.Spec.SecretName != "" {
		if clientSpec.Spec.SecretNamespace == "" {
			clientSpec.Spec.SecretNamespace = req.NamespacedName.Namespace
		}
		// read existing or generate a secret
		value, err := secretmgr.readSecret(r, ctx, clientSpec.Spec.SecretName, clientSpec.Spec.SecretNamespace)
		if err != nil {
			if errors.IsNotFound(err) && clientSpec.Spec.GenerateSecret {
				secret, err := secretmgr.generateSecret(r, ctx, clientSpec.Spec.SecretName, clientSpec.Spec.SecretNamespace)
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

	existing, err := r.DexManager.GetOauth2Client(clientSpec.Spec.Name)
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "not found") {
			ctrl.Log.Info("Client does not exist in Dex. Creating one.", "name", clientSpec.Spec.Name)
			if _, err = r.DexManager.CreateOauth2Client(clientSpec); err != nil {
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
		err = r.DexManager.UpdateOauth2Client(clientSpec)
		if err != nil {
			reqLogger.Error(err, "after UpdateOauth2Client")
			return ctrl.Result{}, err
		}
	}
	return ctrl.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *ClientReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&dexv1alpha1.Client{}).
		Complete(r)
}

// finalizeDeletion removes an OAuth2 client from Dex when the corresponding Client resource is deleted.
// It uses the DexManager to send a request to Dex over gRPC to delete the client.
func (r *ClientReconciler) finalizeDeletion(reqLogger logr.Logger, c *dexv1alpha1.Client, mgr *dexmgr.DexManager) error {
	reqLogger.Info("Client is being removed")
	if _, err := mgr.RemoveOauth2Client(c.Spec.Name); err != nil {
		return err
	}
	return nil
}

func (r *ClientReconciler) getClientSpec(ctx context.Context, namespacedName types.NamespacedName) (*dexv1alpha1.Client, error) {
	clientSpec := &dexv1alpha1.Client{}
	if err := r.Get(ctx, namespacedName, clientSpec); err != nil {
		if errors.IsNotFound(err) {
			return nil, nil
		}
		return nil, err
	}
	return clientSpec, nil
}
