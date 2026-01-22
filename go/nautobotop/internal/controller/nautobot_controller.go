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
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"maps"
	"sort"
	"strings"
	"time"

	nbClient "github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/sync"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"

	"sigs.k8s.io/controller-runtime/pkg/client"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	syncv1alpha1 "github.com/rackerlabs/understack/go/nautobotop/api/v1alpha1"
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
	var nautobotCR syncv1alpha1.Nautobot
	if err := r.Get(ctx, req.NamespacedName, &nautobotCR); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	// Aggregate device type data from all referenced ConfigMaps
	locationTypeMap, err := r.aggregateDeviceTypeDataFromConfigMap(ctx, nautobotCR.Spec.LocationTypesRef)
	if err != nil {
		log.Error(err, "failed to aggregate device type data from ConfigMaps")
		return ctrl.Result{}, err
	}

	// Aggregate device type data from all referenced ConfigMaps
	deviceTypeMap, err := r.aggregateDeviceTypeDataFromConfigMap(ctx, nautobotCR.Spec.DeviceTypesRef)
	if err != nil {
		log.Error(err, "failed to aggregate device type data from ConfigMaps")
		return ctrl.Result{}, err
	}

	// Check if sync should proceed based on time interval and data changes
	syncInterval := time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second
	requestTimeAfter := time.Duration(nautobotCR.Spec.RequeueAfter) * time.Second
	currentHash := computeHash(deviceTypeMap)
	previousHash := nautobotCR.GetSyncHash("deviceType")

	syncDecision := r.shouldSync(nautobotCR.Status.LastSyncedAt, syncInterval, currentHash, previousHash)
	if !syncDecision.ShouldSync {
		log.Info("skipping sync", "reason", syncDecision.Reason, "hash", currentHash)
		nautobotCR.Status.Message = syncDecision.StatusMessage
		if err := r.Status().Update(ctx, &nautobotCR); err != nil {
			log.Error(err, "failed to update status")
			return ctrl.Result{}, err
		}
		return ctrl.Result{RequeueAfter: requestTimeAfter}, nil
	}

	log.Info("proceeding with sync", "reason", syncDecision.Reason, "hash", currentHash)

	// Retrieve the Nautobot authentication token from a secret or external source
	username, token, err := r.getAuthTokenFromSecretRef(ctx, nautobotCR)
	if err != nil {
		log.Error(err, "failed parse find nautobot auth token")
		return ctrl.Result{}, err
	}

	// Create Nautobot client
	nautobotURL := fmt.Sprintf("http://%s.%s.svc.cluster.local/api", nautobotCR.Spec.NautobotServiceRef.Name, nautobotCR.Spec.NautobotServiceRef.Namespace)
	nautobotClient := nbClient.NewNautobotClient(nautobotURL, username, token)

	if err := r.syncLocationTypes(ctx, nautobotClient, locationTypeMap); err != nil {
		log.Error(err, "failed to sync device types")
		return ctrl.Result{}, err
	}
	if err := r.syncDeviceTypes(ctx, nautobotClient, deviceTypeMap); err != nil {
		log.Error(err, "failed to sync device types")
		return ctrl.Result{}, err
	}

	nautobotCR.Status.LastSyncedAt = metav1.Now()
	nautobotCR.Status.Ready = true
	nautobotCR.Status.NautobotStatusReport = nautobotClient.Report
	nautobotCR.SetSyncHash("deviceType", currentHash)
	if len(nautobotClient.Report) > 0 {
		nautobotCR.Status.Message = "sync completed with some errors"
	} else {
		nautobotCR.Status.Message = "Sync Successful"
	}
	if err := r.Status().Update(ctx, &nautobotCR); err != nil {
		log.Error(err, "failed to update status")
		return ctrl.Result{}, err
	}
	// Successfully completed reconciliation; requeue after configured sync interval
	log.Info("sync completed successfully")
	return ctrl.Result{RequeueAfter: requestTimeAfter}, nil
}

// aggregateDeviceTypeDataFromConfigMap fetches and merges data from all referenced ConfigMaps.
// It returns a map containing all device type configurations.
func (r *NautobotReconciler) aggregateDeviceTypeDataFromConfigMap(ctx context.Context, refs []syncv1alpha1.ConfigMapRef) (map[string]string, error) {
	deviceTypeMap := make(map[string]string)

	for _, ref := range refs {
		var configMap corev1.ConfigMap
		namespacedName := types.NamespacedName{
			Name:      ref.ConfigMapSelector.Name,
			Namespace: *ref.ConfigMapSelector.Namespace,
		}

		if err := r.Get(ctx, namespacedName, &configMap); err != nil {
			return nil, fmt.Errorf("failed to fetch ConfigMap %s/%s: %w",
				namespacedName.Namespace, namespacedName.Name, err)
		}

		// Merge ConfigMap data into the aggregate map
		maps.Copy(deviceTypeMap, configMap.Data)
	}

	return deviceTypeMap, nil
}

// syncDeviceTypes syncs device types to Nautobot.
// The hash comparison is now handled in the Reconcile function.
func (r *NautobotReconciler) syncDeviceTypes(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	deviceTypeMap map[string]string,
) error {
	log := logf.FromContext(ctx)

	log.Info("syncing device types", "deviceTypeCount", len(deviceTypeMap))
	syncSvc := sync.NewDeviceTypeSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, deviceTypeMap); err != nil {
		return fmt.Errorf("failed to sync device types: %w", err)
	}

	return nil
}

func (r *NautobotReconciler) syncLocationTypes(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	locationType map[string]string,
) error {
	log := logf.FromContext(ctx)

	log.Info("syncing location types", "locationTypeCount", len(locationType))
	syncSvc := sync.NewLocationTypeSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, locationType); err != nil {
		return fmt.Errorf("failed to sync location types: %w", err)
	}

	return nil
}

// getAuthTokenFromSecretRef: this will fetch Nautobot auth token from the given refer.
func (r *NautobotReconciler) getAuthTokenFromSecretRef(ctx context.Context, nautobotCR syncv1alpha1.Nautobot) (string, string, error) {
	var username, token string
	secret := &corev1.Secret{}
	err := r.Get(ctx, types.NamespacedName{Name: nautobotCR.Spec.NautobotSecretRef.Name, Namespace: *nautobotCR.Spec.NautobotSecretRef.Namespace}, secret)
	if err != nil {
		return "", "", err
	}
	// Read the secret value
	if valBytes, ok := secret.Data[nautobotCR.Spec.NautobotSecretRef.UsernameKey]; ok {
		username = string(valBytes)
	}
	if valBytes, ok := secret.Data[nautobotCR.Spec.NautobotSecretRef.TokenKey]; ok {
		token = string(valBytes)
	}

	if username != "" || token != "" {
		return username, token, nil
	}

	return "", "", fmt.Errorf("secret keys not found in provide secret")
}

// SetupWithManager sets up the controller with the Manager.
func (r *NautobotReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&syncv1alpha1.Nautobot{}).
		Named("nautobot").
		Complete(r)
}

// SyncDecision represents the result of evaluating whether a sync should proceed
type SyncDecision struct {
	ShouldSync         bool
	Reason             string
	StatusMessage      string
	RequeueAfter       time.Duration
	UpdateLastSyncTime bool
}

// shouldSync determines whether a sync operation should proceed based on time interval and data changes.
// It returns a SyncDecision with the recommendation and associated metadata.
//
// Logic:
// - If data has changed (hash mismatch), sync immediately regardless of time interval
// - If data hasn't changed and time interval hasn't elapsed, skip sync
// - If data hasn't changed but time interval has elapsed, proceed with sync
func (r *NautobotReconciler) shouldSync(lastSyncedAt metav1.Time, syncInterval time.Duration, currentHash, previousHash string) SyncDecision {
	dataChanged := currentHash != previousHash

	// If data has changed, always sync regardless of time interval
	if dataChanged {
		return SyncDecision{
			ShouldSync:         true,
			Reason:             "data changed",
			StatusMessage:      "Syncing due to data changes",
			RequeueAfter:       syncInterval,
			UpdateLastSyncTime: false,
		}
	}

	// Data hasn't changed, check time interval
	if !lastSyncedAt.IsZero() {
		timeSinceLastSync := time.Since(lastSyncedAt.Time)
		if timeSinceLastSync < syncInterval {
			remainingTime := syncInterval - timeSinceLastSync
			return SyncDecision{
				ShouldSync:         false,
				Reason:             "sync interval not elapsed",
				StatusMessage:      "Sync skipped - interval not elapsed",
				RequeueAfter:       remainingTime,
				UpdateLastSyncTime: false,
			}
		}
	}

	// Data hasn't changed but time interval has elapsed (or this is first sync)
	return SyncDecision{
		ShouldSync:         true,
		Reason:             "sync interval elapsed",
		StatusMessage:      "Syncing due to elapsed interval",
		RequeueAfter:       syncInterval,
		UpdateLastSyncTime: false,
	}
}

// computeHash returns a stable SHA-256 hash of the map contents
func computeHash(m map[string]string) string {
	if len(m) == 0 {
		return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" // sha256 of empty
	}

	// Get sorted keys for deterministic order
	keys := []string{}
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	// Build canonical string: "key1=value1\nkey2=value2\n..."
	var sb strings.Builder
	for i, k := range keys {
		if i > 0 {
			sb.WriteByte('\n')
		}
		// Escape newlines and backslashes if you want to be extra safe
		// Or just write raw — usually fine for ConfigMap data
		sb.WriteString(k)
		sb.WriteByte('=')
		sb.WriteString(m[k])
	}

	hash := sha256.Sum256([]byte(sb.String()))
	return hex.EncodeToString(hash[:])
}
