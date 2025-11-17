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
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"

	"sigs.k8s.io/controller-runtime/pkg/client"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	syncv1alpha1 "github.com/rackerlabs/understack/go/sync/api/v1alpha1"
	"github.com/rackerlabs/understack/go/sync/internal/nautobot"
)

// NautobotReconciler reconciles a Nautobot object
type NautobotReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=sync.rax.io,resources=nautobots,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=sync.rax.io,resources=nautobots/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=sync.rax.io,resources=nautobots/finalizers,verbs=update

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
// TODO(user): Modify the Reconcile function to compare the state specified by
// the Nautobot object against the actual cluster state, and then
// perform operations to make the cluster state reflect the state specified by
// the user.
//
// For more details, check Reconcile and its Result here:
// - https://pkg.go.dev/sigs.k8s.io/controller-runtime@v0.20.4/pkg/reconcile
func (r *NautobotReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := logf.FromContext(ctx)
	// Fetch the Nautobot custom resource instance
	var nautobotCR syncv1alpha1.Nautobot
	if err := r.Get(ctx, types.NamespacedName{Name: req.Name}, &nautobotCR); err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, client.IgnoreNotFound(err)
	}

	// Fetch the Nautobot nautobotService to get its ClusterIP
	var nautobotService corev1.Service
	if err := r.Get(ctx, types.NamespacedName{Namespace: "default", Name: "nautobot-default"}, &nautobotService); err != nil {
		log.Error(err, "failed to fetch Service nautobot-default")
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
	}

	// Retrieve the Nautobot authentication token from a secret or external source
	nautobotAuthToken, err := r.getAuthTokenFromSecretRef(ctx, nautobotCR, "NAUTOBOT_SUPERUSER_API_TOKEN")
	if err != nil {
		log.Error(err, "failed parse find nautoBotAuthToken")
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
	}

	deviceTypeMap := make(map[string]string)
	for _, ref := range nautobotCR.Spec.DeviceTypesRef {
		var deviceTypeConfigMap corev1.ConfigMap
		err = r.Get(ctx, types.NamespacedName{
			Namespace: *ref.ConfigMapSelector.Namespace,
			Name:      ref.ConfigMapSelector.Name,
		}, &deviceTypeConfigMap)
		if err != nil {
			log.Error(err, "failed to fetch ConfigMap 'deviceType' in namespace 'nautobot'")
			return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
		}
		for k, v := range deviceTypeConfigMap.Data {
			deviceTypeMap[k] = v
		}
	}

	n := nautobot.NewNautobotClient(fmt.Sprintf("http://%s/api", nautobotService.Spec.ClusterIP), nautobotAuthToken)
	n.SyncAllDeviceTypes(ctx, deviceTypeMap)
	// Update status
	nautobotCR.Status.LastSyncedAt = metav1.Now()
	nautobotCR.Status.Ready = true
	nautobotCR.Status.Message = "Sync successful"
	if err := r.Status().Update(ctx, &nautobotCR); err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
	}
	// Successfully completed reconciliation; requeue after configured sync interval
	return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, nil
}

// getAuthTokenFromSecretRef: this will fetch Nautobot auth token from the given refer.
func (r *NautobotReconciler) getAuthTokenFromSecretRef(ctx context.Context, nautobotCR syncv1alpha1.Nautobot, name string) (string, error) {
	secret := &corev1.Secret{}
	err := r.Get(ctx, types.NamespacedName{Name: nautobotCR.Spec.NautobotSecretRef.Name, Namespace: *nautobotCR.Spec.NautobotSecretRef.Namespace}, secret)
	if err != nil {
		return "", err
	}
	// Read the secret value
	if valBytes, ok := secret.Data[nautobotCR.Spec.NautobotSecretRef.Key]; ok {
		return string(valBytes), nil
	}
	return "", fmt.Errorf("secret key %s not found in secret", nautobotCR.Spec.NautobotSecretRef.Key)
}

// SetupWithManager sets up the controller with the Manager.
func (r *NautobotReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&syncv1alpha1.Nautobot{}).
		Named("nautobot").
		Complete(r)
}
