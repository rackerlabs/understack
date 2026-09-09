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
	syncadmin "github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/sync/admin"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"

	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/handler"
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
type resourceConfig struct {
	name       string
	dependsOn  []string
	configRefs []syncv1alpha1.ConfigMapRef
	syncFunc   func(context.Context, *nbClient.NautobotClient, map[string]string) error
}

func (r *NautobotReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := logf.FromContext(ctx)
	var nautobotCR syncv1alpha1.Nautobot
	if err := r.Get(ctx, req.NamespacedName, &nautobotCR); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	requeueAfter := time.Duration(nautobotCR.Spec.RequeueAfter) * time.Second

	if !nautobotCR.Spec.IsEnabled {
		log.Info("reconciliation is disabled for this resource", "name", req.NamespacedName)
		return ctrl.Result{RequeueAfter: requeueAfter}, nil
	}

	syncInterval := time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second

	// Define all resources to sync with explicit dependency declarations.
	// Order in this slice does NOT matter — topological sort determines execution order.
	resources := []resourceConfig{
		// No dependencies
		{name: "locationTypes", configRefs: nautobotCR.Spec.LocationTypesRef, syncFunc: r.syncLocationTypes},
		{name: "rir", configRefs: nautobotCR.Spec.RirRef, syncFunc: r.syncRir},
		{name: "role", configRefs: nautobotCR.Spec.RoleRef, syncFunc: r.syncRole},
		{name: "deviceType", configRefs: nautobotCR.Spec.DeviceTypesRef, syncFunc: r.syncDeviceTypes},
		{name: "tenantGroup", configRefs: nautobotCR.Spec.TenantGroupRef, syncFunc: r.syncTenantGroup},
		{name: "clusterType", configRefs: nautobotCR.Spec.ClusterTypeRef, syncFunc: r.syncClusterType},
		{name: "clusterGroup", configRefs: nautobotCR.Spec.ClusterGroupRef, syncFunc: r.syncClusterGroup},
		// Depends on: locationTypes
		{name: "location", dependsOn: []string{"locationTypes"}, configRefs: nautobotCR.Spec.LocationRef, syncFunc: r.syncLocation},
		// Depends on: tenantGroup
		{name: "tenant", dependsOn: []string{"tenantGroup"}, configRefs: nautobotCR.Spec.TenantRef, syncFunc: r.syncTenant},
		// Depends on: location
		{name: "rackGroup", dependsOn: []string{"location"}, configRefs: nautobotCR.Spec.RackGroupRef, syncFunc: r.syncRackGroup},
		{name: "vlanGroup", dependsOn: []string{"location"}, configRefs: nautobotCR.Spec.VlanGroupRef, syncFunc: r.syncVlanGroup},
		// Depends on: location, rackGroup
		{name: "rack", dependsOn: []string{"location", "rackGroup"}, configRefs: nautobotCR.Spec.RackRef, syncFunc: r.syncRack},
		// Depends on: location, tenant
		{name: "namespace", dependsOn: []string{"location", "tenant"}, configRefs: nautobotCR.Spec.NamespaceRef, syncFunc: r.syncNamespace},
		// Depends on: deviceType, location, rack, role, tenant
		{name: "device", dependsOn: []string{"deviceType", "location", "rack", "role", "tenant"}, configRefs: nautobotCR.Spec.DeviceRef, syncFunc: r.syncDevice},
		// Depends on: vlanGroup, location, tenant, role
		{name: "vlan", dependsOn: []string{"vlanGroup", "location", "tenant", "role"}, configRefs: nautobotCR.Spec.VlanRef, syncFunc: r.syncVlan},
		// Depends on: clusterType, clusterGroup, location, device
		{name: "cluster", dependsOn: []string{"clusterType", "clusterGroup", "location", "device"}, configRefs: nautobotCR.Spec.ClusterRef, syncFunc: r.syncCluster},
		// Depends on: namespace, rir, location, vlan, tenant, role
		{name: "prefix", dependsOn: []string{"namespace", "rir", "location", "vlan", "tenant", "role"}, configRefs: nautobotCR.Spec.PrefixRef, syncFunc: r.syncPrefix},
		{name: "permissionGroup", configRefs: nautobotCR.Spec.PermissionGroupRef, syncFunc: r.syncPermissionGroup},
	}

	// Resolve execution order using topological sort (Kahn's algorithm)
	dagNodes := make([]ResourceNode, len(resources))
	for i, res := range resources {
		dagNodes[i] = ResourceNode{Name: res.name, DependsOn: res.dependsOn}
	}
	topologicalSort, err := topologicalSort(dagNodes)
	if err != nil {
		log.Error(err, "failed to resolve resource sync order")
		return ctrl.Result{}, err
	}

	// Build lookup for quick access by name
	resourceByName := make(map[string]resourceConfig, len(resources))
	for _, res := range resources {
		resourceByName[res.name] = res
	}

	// Reorder resources according to topological sort result
	orderedResources := make([]resourceConfig, 0, len(topologicalSort))
	for _, name := range topologicalSort {
		orderedResources = append(orderedResources, resourceByName[name])
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

	// Validate nautobotSecretRef before attempting auth
	if nautobotCR.Spec.NautobotSecretRef.Name == "" {
		log.Info("nautobotSecretRef.Name is not configured, skipping sync")
		nautobotCR.Status.Ready = false
		nautobotCR.Status.Message = "nautobotSecretRef is not configured: secret name is required"
		if err := r.Status().Update(ctx, &nautobotCR); err != nil {
			log.Error(err, "failed to update status")
			return ctrl.Result{}, err
		}
		return ctrl.Result{RequeueAfter: requeueAfter}, nil
	}

	// Create Nautobot client. The not-configured case (empty secret name) is
	// handled by the validation above; any error here is a genuine failure
	// (RBAC, wrong namespace, API error, missing keys) and must be surfaced
	// so backoff and the reconcile-error metric kick in.
	username, token, err := r.getAuthTokenFromSecretRef(ctx, nautobotCR)
	if err != nil {
		log.Error(err, "failed to get nautobot auth token")
		nautobotCR.Status.Ready = false
		nautobotCR.Status.Message = fmt.Sprintf("failed to get authentication token: %v", err)
		if statusErr := r.Status().Update(ctx, &nautobotCR); statusErr != nil {
			log.Error(statusErr, "failed to update status after auth error")
		}
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
		nautobotClient.Cache.Close()
		nautobotClient.ReqClient.GetClient().CloseIdleConnections()
		log.Info("released cache and idle connections after reconcile")
	}()

	// Sync resources that need updating (in topologically sorted order)
	for _, res := range orderedResources {
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
		if ref.ConfigMapSelector.Namespace == nil || *ref.ConfigMapSelector.Namespace == "" {
			return nil, fmt.Errorf("configMapSelector %q is missing a namespace", ref.ConfigMapSelector.Name)
		}
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
	log.Info("starting sync of device types", "totalEntriesDefined", len(deviceTypeMap))
	if len(deviceTypeMap) == 0 {
		return nil
	}
	syncSvc := sync.NewDeviceTypeSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, deviceTypeMap); err != nil {
		return fmt.Errorf("failed to sync device types: %w", err)
	}
	log.Info("completed sync of device types")
	return nil
}

func (r *NautobotReconciler) syncRackGroup(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	rackGroup map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of rack groups", "totalEntriesDefined", len(rackGroup))
	if len(rackGroup) == 0 {
		return nil
	}
	syncSvc := sync.NewRackGroupSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, rackGroup); err != nil {
		return fmt.Errorf("failed to sync rack group: %w", err)
	}
	log.Info("completed sync of rack groups")
	return nil
}

func (r *NautobotReconciler) syncRack(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	rackData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of racks", "totalEntriesDefined", len(rackData))
	if len(rackData) == 0 {
		return nil
	}
	syncSvc := sync.NewRackSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, rackData); err != nil {
		return fmt.Errorf("failed to sync racks: %w", err)
	}
	log.Info("completed sync of racks")
	return nil
}

func (r *NautobotReconciler) syncPermissionGroup(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	permissionGroupData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of permission groups", "totalEntriesDefined", len(permissionGroupData))
	if len(permissionGroupData) == 0 {
		return nil
	}
	syncSvc := syncadmin.NewPermissionGroupSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, permissionGroupData); err != nil {
		return fmt.Errorf("failed to sync permission groups: %w", err)
	}
	log.Info("completed sync of permission groups")
	return nil
}

func (r *NautobotReconciler) syncLocation(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	locationType map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of locations", "totalEntriesDefined", len(locationType))
	if len(locationType) == 0 {
		return nil
	}
	syncSvc := sync.NewLocationSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, locationType); err != nil {
		return fmt.Errorf("failed to sync location types: %w", err)
	}
	log.Info("completed sync of locations")
	return nil
}

func (r *NautobotReconciler) syncLocationTypes(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	locationType map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of location types", "totalEntriesDefined", len(locationType))
	if len(locationType) == 0 {
		return nil
	}
	syncSvc := sync.NewLocationTypeSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, locationType); err != nil {
		return fmt.Errorf("failed to sync location types: %w", err)
	}
	log.Info("completed sync of location types")
	return nil
}

func (r *NautobotReconciler) syncVlanGroup(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	vlanGroupData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of vlan groups", "totalEntriesDefined", len(vlanGroupData))
	if len(vlanGroupData) == 0 {
		return nil
	}
	syncSvc := sync.NewVlanGroupSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, vlanGroupData); err != nil {
		return fmt.Errorf("failed to sync vlan groups: %w", err)
	}
	log.Info("completed sync of vlan groups")
	return nil
}

func (r *NautobotReconciler) syncVlan(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	vlanData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of vlans", "totalEntriesDefined", len(vlanData))
	if len(vlanData) == 0 {
		return nil
	}
	syncSvc := sync.NewVlanSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, vlanData); err != nil {
		return fmt.Errorf("failed to sync vlans: %w", err)
	}
	log.Info("completed sync of vlans")
	return nil
}

func (r *NautobotReconciler) syncPrefix(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	prefixData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of prefixes", "totalEntriesDefined", len(prefixData))
	if len(prefixData) == 0 {
		return nil
	}
	syncSvc := sync.NewPrefixSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, prefixData); err != nil {
		return fmt.Errorf("failed to sync prefixes: %w", err)
	}
	log.Info("completed sync of prefixes")
	return nil
}

func (r *NautobotReconciler) syncClusterType(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	clusterTypeData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of cluster types", "totalEntriesDefined", len(clusterTypeData))
	if len(clusterTypeData) == 0 {
		return nil
	}
	syncSvc := sync.NewClusterTypeSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, clusterTypeData); err != nil {
		return fmt.Errorf("failed to sync cluster types: %w", err)
	}
	log.Info("completed sync of cluster types")
	return nil
}

func (r *NautobotReconciler) syncClusterGroup(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	clusterGroupData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of cluster groups", "totalEntriesDefined", len(clusterGroupData))
	if len(clusterGroupData) == 0 {
		return nil
	}
	syncSvc := sync.NewClusterGroupSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, clusterGroupData); err != nil {
		return fmt.Errorf("failed to sync cluster groups: %w", err)
	}
	log.Info("completed sync of cluster groups")
	return nil
}

func (r *NautobotReconciler) syncCluster(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	clusterData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of clusters", "totalEntriesDefined", len(clusterData))
	if len(clusterData) == 0 {
		return nil
	}
	syncSvc := sync.NewClusterSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, clusterData); err != nil {
		return fmt.Errorf("failed to sync clusters: %w", err)
	}
	log.Info("completed sync of clusters")
	return nil
}
func (r *NautobotReconciler) syncNamespace(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	namespaceData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of namespaces", "totalEntriesDefined", len(namespaceData))
	if len(namespaceData) == 0 {
		return nil
	}
	syncSvc := sync.NewNamespaceSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, namespaceData); err != nil {
		return fmt.Errorf("failed to sync namespaces: %w", err)
	}
	log.Info("completed sync of namespaces")
	return nil
}

func (r *NautobotReconciler) syncRir(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	rirData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of rirs", "totalEntriesDefined", len(rirData))
	if len(rirData) == 0 {
		return nil
	}
	syncSvc := sync.NewRirSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, rirData); err != nil {
		return fmt.Errorf("failed to sync rirs: %w", err)
	}
	log.Info("completed sync of rirs")
	return nil
}

func (r *NautobotReconciler) syncRole(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	roleData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of roles", "totalEntriesDefined", len(roleData))
	if len(roleData) == 0 {
		return nil
	}
	syncSvc := sync.NewRoleSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, roleData); err != nil {
		return fmt.Errorf("failed to sync roles: %w", err)
	}
	log.Info("completed sync of roles")
	return nil
}

func (r *NautobotReconciler) syncTenantGroup(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	tenantGroupData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of tenant groups", "totalEntriesDefined", len(tenantGroupData))
	if len(tenantGroupData) == 0 {
		return nil
	}
	syncSvc := sync.NewTenantGroupSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, tenantGroupData); err != nil {
		return fmt.Errorf("failed to sync tenant groups: %w", err)
	}
	log.Info("completed sync of tenant groups")
	return nil
}

func (r *NautobotReconciler) syncTenant(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	tenantData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of tenants", "totalEntriesDefined", len(tenantData))
	if len(tenantData) == 0 {
		return nil
	}
	syncSvc := sync.NewTenantSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, tenantData); err != nil {
		return fmt.Errorf("failed to sync tenants: %w", err)
	}
	log.Info("completed sync of tenants")
	return nil
}

func (r *NautobotReconciler) syncDevice(ctx context.Context,
	nautobotClient *nbClient.NautobotClient,
	deviceData map[string]string,
) error {
	log := logf.FromContext(ctx)
	log.Info("starting sync of devices", "totalEntriesDefined", len(deviceData))
	if len(deviceData) == 0 {
		return nil
	}
	syncSvc := sync.NewDeviceSync(nautobotClient)
	if err := syncSvc.SyncAll(ctx, deviceData); err != nil {
		return fmt.Errorf("failed to sync devices: %w", err)
	}
	log.Info("completed sync of devices")
	return nil
}

// getAuthTokenFromSecretRef fetches the Nautobot auth token from the referenced Secret.
// If Namespace is not set on the secret ref, it falls back to NautobotServiceRef.Namespace.
func (r *NautobotReconciler) getAuthTokenFromSecretRef(ctx context.Context, nautobotCR syncv1alpha1.Nautobot) (string, string, error) {
	ref := nautobotCR.Spec.NautobotSecretRef

	// Caller should have already validated Name, but be defensive
	if ref.Name == "" {
		return "", "", fmt.Errorf("nautobotSecretRef name is empty")
	}

	// Default namespace: use NautobotServiceRef.Namespace as a fallback
	// (since the CRD is cluster-scoped and has no inherent namespace)
	namespace := nautobotCR.Spec.NautobotServiceRef.Namespace
	if ref.Namespace != nil && *ref.Namespace != "" {
		namespace = *ref.Namespace
	}

	if namespace == "" {
		return "", "", fmt.Errorf("nautobotSecretRef %q is missing a namespace and no fallback namespace is available", ref.Name)
	}

	secret := &corev1.Secret{}
	if err := r.Get(ctx, types.NamespacedName{Name: ref.Name, Namespace: namespace}, secret); err != nil {
		return "", "", fmt.Errorf("failed to fetch secret %s/%s: %w", namespace, ref.Name, err)
	}

	var username, token string
	if valBytes, ok := secret.Data[ref.UsernameKey]; ok {
		username = string(valBytes)
	}
	if valBytes, ok := secret.Data[ref.TokenKey]; ok {
		token = string(valBytes)
	}

	if username == "" && token == "" {
		return "", "", fmt.Errorf("secret keys %q/%q not found in secret %s/%s", ref.UsernameKey, ref.TokenKey, namespace, ref.Name)
	}

	return username, token, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *NautobotReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&syncv1alpha1.Nautobot{}).
		Watches(&corev1.ConfigMap{}, handler.EnqueueRequestsFromMapFunc(r.configMapToNautobotRequests)).
		WithOptions(controller.Options{RecoverPanic: ptr.To(true)}).
		Named("nautobot").
		Complete(r)
}

// configMapToNautobotRequests maps a changed ConfigMap to the Nautobot CR(s) that reference it.
func (r *NautobotReconciler) configMapToNautobotRequests(ctx context.Context, obj client.Object) []ctrl.Request {
	log := logf.FromContext(ctx)

	var nautobotList syncv1alpha1.NautobotList
	if err := r.List(ctx, &nautobotList); err != nil {
		log.Error(err, "failed to list Nautobot CRs for ConfigMap watch")
		return nil
	}

	var requests []ctrl.Request
	for i := range nautobotList.Items {
		nb := &nautobotList.Items[i]
		if r.referencesConfigMap(nb, obj.GetName(), obj.GetNamespace()) {
			requests = append(requests, ctrl.Request{
				NamespacedName: types.NamespacedName{
					Name: nb.Name,
				},
			})
		}
	}

	if len(requests) > 0 {
		log.Info("ConfigMap change triggered reconcile", "configMap", obj.GetName(), "namespace", obj.GetNamespace(), "matchedCRs", len(requests))
	}

	return requests
}

// referencesConfigMap checks whether a Nautobot CR references the given ConfigMap by name and namespace.
func (r *NautobotReconciler) referencesConfigMap(nb *syncv1alpha1.Nautobot, name, namespace string) bool {
	for _, ref := range nb.Spec.ConfigMapRefs() {
		if ref.ConfigMapSelector.Name == name {
			refNS := ""
			if ref.ConfigMapSelector.Namespace != nil {
				refNS = *ref.ConfigMapSelector.Namespace
			}
			if refNS == namespace {
				return true
			}
		}
	}
	return false
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
