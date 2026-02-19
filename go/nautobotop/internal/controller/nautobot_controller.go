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
// resourceConfig defines configuration for a single resource type
type resourceConfig struct {
	name       string
	configRefs []syncv1alpha1.ConfigMapRef
	syncFunc   func(context.Context, *nbClient.NautobotClient, map[string]string) error
}

func (r *NautobotReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := logf.FromContext(ctx)
	var nautobotCR syncv1alpha1.Nautobot
	if err := r.Get(ctx, req.NamespacedName, &nautobotCR); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	syncInterval := time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second
	requeueAfter := time.Duration(nautobotCR.Spec.RequeueAfter) * time.Second

	// Define all resources to sync
	// Add more resources here: {name: "location", configRefs: nautobotCR.Spec.LocationsRef, syncFunc: r.syncLocations}
	resources := []resourceConfig{
		{name: "locationType", configRefs: nautobotCR.Spec.LocationTypesRef, syncFunc: r.syncLocationTypes},
		{name: "location", configRefs: nautobotCR.Spec.LocationRef, syncFunc: r.syncLocation},
		{name: "rackGroup", configRefs: nautobotCR.Spec.RackGroupRef, syncFunc: r.syncRackGroup},
		{name: "rack", configRefs: nautobotCR.Spec.RackRef, syncFunc: r.syncRack},
		{name: "deviceType", configRefs: nautobotCR.Spec.DeviceTypesRef, syncFunc: r.syncDeviceTypes},
	}

	// Aggregate data and check sync decisions for all resources
	resourcesToSync := make(map[string]map[string]string)
	for _, res := range resources {
		dataMap, err := r.aggregateDataFromConfigMap(ctx, res.configRefs)
		if err != nil {
			log.Error(err, "failed to aggregate data", "resource", res.name)
			return ctrl.Result{}, err
		}

		currentHash := computeHash(dataMap)
		previousHash := nautobotCR.GetSyncHash(res.name)
		decision := r.shouldSync(nautobotCR.Status.LastSyncedAt, syncInterval, currentHash, previousHash)

		if decision.ShouldSync {
			log.Info("resource needs sync", "resource", res.name, "reason", decision.Reason)
			resourcesToSync[res.name] = dataMap
		} else {
			log.Info("skipping resource sync", "resource", res.name, "reason", decision.Reason)
		}
	}

	// If nothing to sync, update status and requeue
	if len(resourcesToSync) == 0 {
		nautobotCR.Status.Message = "No changes detected"
		if err := r.Status().Update(ctx, &nautobotCR); err != nil {
			log.Error(err, "failed to update status")
			return ctrl.Result{}, err
		}
		return ctrl.Result{RequeueAfter: requeueAfter}, nil
	}

	// Create Nautobot client
	username, token, err := r.getAuthTokenFromSecretRef(ctx, nautobotCR)
	if err != nil {
		log.Error(err, "failed to get nautobot auth token")
		return ctrl.Result{}, err
	}
	nautobotURL := fmt.Sprintf("http://%s.%s.svc.cluster.local/api", nautobotCR.Spec.NautobotServiceRef.Name, nautobotCR.Spec.NautobotServiceRef.Namespace)
	nautobotClient, err := nbClient.NewNautobotClient(nautobotURL, username, token, nautobotCR.Spec.CacheMaxSize)
	if err != nil {
		log.Error(err, "failed to create nautobot client")
		return ctrl.Result{}, err
	}

	if err := nautobotClient.PreLoadCacheForLookup(ctx); err != nil {
		log.Error(err, "failed to warmup cache")
	}
	defer func() {
		nautobotClient.Cache.Clear()
		log.Info("cleared cache after reconcile")
	}()

	// Sync resources that need updating
	for _, res := range resources {
		if dataMap, ok := resourcesToSync[res.name]; ok {
			if err := res.syncFunc(ctx, nautobotClient, dataMap); err != nil {
				log.Error(err, "failed to sync resource", "resource", res.name)
				return ctrl.Result{}, err
			}
			nautobotCR.SetSyncHash(res.name, computeHash(dataMap))
		}
	}

	// Update status
	nautobotCR.Status.LastSyncedAt = metav1.Now()
	nautobotCR.Status.Ready = true
	nautobotCR.Status.NautobotStatusReport = nautobotClient.Report
	if len(nautobotClient.Report) > 0 {
		nautobotCR.Status.Message = "sync completed with some errors"
	} else {
		nautobotCR.Status.Message = "Sync Successful"
	}
	if err := r.Status().Update(ctx, &nautobotCR); err != nil {
		log.Error(err, "failed to update status")
		return ctrl.Result{}, err
	}

	log.Info("sync completed successfully")
	return ctrl.Result{RequeueAfter: requeueAfter}, nil
}

// aggregateDataFromConfigMap fetches and merges data from all referenced ConfigMaps.
func (r *NautobotReconciler) aggregateDataFromConfigMap(ctx context.Context, refs []syncv1alpha1.ConfigMapRef) (map[string]string, error) {
	dataMap := make(map[string]string)

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

		maps.Copy(dataMap, configMap.Data)
	}

	return dataMap, nil
}

// syncDeviceTypes syncs device types to Nautobot.
func (r *NautobotReconciler) syncDeviceTypes(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	deviceTypeMap map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("syncing device types", "count", len(deviceTypeMap))
	if len(deviceTypeMap) == 0 {
		return nil
	}
	syncSvc := sync.NewDeviceTypeSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, deviceTypeMap); err != nil {
		return fmt.Errorf("failed to sync device types: %w", err)
	}
	return nil
}

func (r *NautobotReconciler) syncRackGroup(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	rackGroup map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("syncing rack group", "count", len(rackGroup))
	if len(rackGroup) == 0 {
		return nil
	}
	syncSvc := sync.NewRackGroupSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, rackGroup); err != nil {
		return fmt.Errorf("failed to sync rack group: %w", err)
	}
	return nil
}

func (r *NautobotReconciler) syncRack(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	rackData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("syncing racks", "count", len(rackData))
	if len(rackData) == 0 {
		return nil
	}
	syncSvc := sync.NewRackSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, rackData); err != nil {
		return fmt.Errorf("failed to sync racks: %w", err)
	}
	return nil
}

func (r *NautobotReconciler) syncLocation(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	locationType map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("syncing location types", "count", len(locationType))
	if len(locationType) == 0 {
		return nil
	}
	syncSvc := sync.NewLocationSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, locationType); err != nil {
		return fmt.Errorf("failed to sync location types: %w", err)
	}
	return nil
}

func (r *NautobotReconciler) syncLocationTypes(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	locationType map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("syncing location types", "count", len(locationType))
	if len(locationType) == 0 {
		return nil
	}
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
