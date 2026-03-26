package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/virtualization"
	"github.com/samber/lo"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"go.yaml.in/yaml/v3"
)

type ClusterSync struct {
	client          *client.NautobotClient
	clusterSvc      *virtualization.ClusterService
	clusterTypeSvc  *virtualization.ClusterTypeService
	clusterGroupSvc *virtualization.ClusterGroupService
	locationSvc     *dcim.LocationService
	deviceSvc       *dcim.DeviceService
}

func NewClusterSync(nautobotClient *client.NautobotClient) *ClusterSync {
	return &ClusterSync{
		client:          nautobotClient.GetClient(),
		clusterSvc:      virtualization.NewClusterService(nautobotClient.GetClient()),
		clusterTypeSvc:  virtualization.NewClusterTypeService(nautobotClient.GetClient()),
		clusterGroupSvc: virtualization.NewClusterGroupService(nautobotClient.GetClient()),
		locationSvc:     dcim.NewLocationService(nautobotClient.GetClient()),
		deviceSvc:       dcim.NewDeviceService(nautobotClient.GetClient()),
	}
}

func (s *ClusterSync) SyncAll(ctx context.Context, data map[string]string) error {
	var clusters models.Clusters
	for key, f := range data {
		var yml []models.Cluster
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		clusters.Cluster = append(clusters.Cluster, yml...)
	}

	for _, cluster := range clusters.Cluster {
		if err := s.syncSingleCluster(ctx, cluster); err != nil {
			return err
		}
	}
	s.deleteObsoleteClusters(ctx, clusters)

	return nil
}

// syncSingleCluster handles the create/update logic for a single cluster and its devices
func (s *ClusterSync) syncSingleCluster(ctx context.Context, cluster models.Cluster) error {
	existingCluster := s.clusterSvc.GetByName(ctx, cluster.Name)

	// Build cluster type reference (required)
	clusterTypeRef, err := s.buildClusterTypeReference(ctx, cluster.ClusterType)
	if err != nil {
		return fmt.Errorf("failed to build cluster type reference for cluster %s: %w", cluster.Name, err)
	}

	clusterRequest := nb.ClusterRequest{
		Name:        cluster.Name,
		Comments:    nb.PtrString(cluster.Comments),
		ClusterType: clusterTypeRef,
	}

	if cluster.ClusterGroup != "" {
		clusterGroupRef, err := s.buildClusterGroupReference(ctx, cluster.ClusterGroup)
		if err != nil {
			return fmt.Errorf("failed to build cluster group reference for cluster %s: %w", cluster.Name, err)
		}
		clusterRequest.ClusterGroup = clusterGroupRef
	}

	if cluster.Location != "" {
		clusterRequest.Location = s.buildLocationReference(ctx, cluster.Location)
	}

	var clusterID *string
	if existingCluster.Id == nil {
		clusterID, err = s.createCluster(ctx, clusterRequest)
		if err != nil {
			return err
		}
	} else if !helpers.CompareJSONFields(existingCluster, clusterRequest) {
		clusterID, err = s.updateCluster(ctx, *existingCluster.Id, clusterRequest)
		if err != nil {
			return err
		}
	} else {
		log.Info("cluster unchanged, skipping update", "name", clusterRequest.Name)
		clusterID = existingCluster.Id
	}

	// Sync devices for this cluster
	if clusterID != nil && len(cluster.Devices) > 0 {
		s.syncClusterDevices(ctx, *clusterID, cluster.Devices)
	}

	return nil
}

// createCluster creates a new cluster in Nautobot
func (s *ClusterSync) createCluster(ctx context.Context, request nb.ClusterRequest) (*string, error) {
	createdCluster, err := s.clusterSvc.Create(ctx, request)
	if err != nil || createdCluster == nil {
		return nil, fmt.Errorf("failed to create cluster %s: %w", request.Name, err)
	}
	log.Info("cluster created", "name", request.Name)
	return createdCluster.Id, nil
}

// updateCluster updates an existing cluster in Nautobot
func (s *ClusterSync) updateCluster(ctx context.Context, id string, request nb.ClusterRequest) (*string, error) {
	updatedCluster, err := s.clusterSvc.Update(ctx, id, request)
	if err != nil || updatedCluster == nil {
		return nil, fmt.Errorf("failed to update cluster %s: %w", request.Name, err)
	}
	log.Info("cluster updated", "name", request.Name)
	return updatedCluster.Id, nil
}

// syncClusterDevices assigns desired devices to the cluster and unassigns devices no longer listed
func (s *ClusterSync) syncClusterDevices(ctx context.Context, clusterID string, desiredDeviceNames []string) {
	// Resolve desired device names to IDs
	desiredDeviceIDs := make(map[string]string) // name -> id
	for _, deviceName := range desiredDeviceNames {
		device := s.deviceSvc.GetByName(ctx, deviceName)
		if device.Id == nil {
			s.client.AddReport("syncClusterDevices", "device not found: "+deviceName)
			continue
		}
		desiredDeviceIDs[deviceName] = *device.Id
	}

	// Get currently assigned devices
	currentDevices := s.deviceSvc.ListByCluster(ctx, clusterID)
	currentDeviceIDs := make(map[string]string) // name -> id
	for _, device := range currentDevices {
		currentDeviceIDs[device.GetName()] = *device.Id
	}

	// Assign devices that should be in the cluster but aren't
	for name, id := range desiredDeviceIDs {
		if _, exists := currentDeviceIDs[name]; !exists {
			if err := s.deviceSvc.AssignToCluster(ctx, id, &clusterID); err != nil {
				log.Error("failed to assign device to cluster", "device", name, "error", err)
			} else {
				log.Info("device assigned to cluster", "device", name)
			}
		}
	}

	// Unassign devices that are in the cluster but shouldn't be
	for name, id := range currentDeviceIDs {
		if _, exists := desiredDeviceIDs[name]; !exists {
			if err := s.deviceSvc.AssignToCluster(ctx, id, nil); err != nil {
				log.Error("failed to unassign device from cluster", "device", name, "error", err)
			} else {
				log.Info("device unassigned from cluster", "device", name)
			}
		}
	}
}

// deleteObsoleteClusters removes clusters that are not defined in YAML
func (s *ClusterSync) deleteObsoleteClusters(ctx context.Context, clusters models.Clusters) {
	desiredClusters := make(map[string]models.Cluster)
	for _, cluster := range clusters.Cluster {
		desiredClusters[cluster.Name] = cluster
	}

	existingClusters := s.clusterSvc.ListAll(ctx)
	existingMap := make(map[string]nb.Cluster, len(existingClusters))
	for _, cluster := range existingClusters {
		existingMap[cluster.Name] = cluster
	}

	obsoleteClusters := lo.OmitByKeys(existingMap, lo.Keys(desiredClusters))
	for _, obsoleteCluster := range obsoleteClusters {
		if obsoleteCluster.Id != nil {
			err := s.clusterSvc.Destroy(ctx, *obsoleteCluster.Id)
			if err != nil {
				log.Error("failed to delete obsolete cluster", "name", obsoleteCluster.Name)
			}
		}
	}
}

func (s *ClusterSync) buildClusterTypeReference(ctx context.Context, name string) (nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	clusterType := s.clusterTypeSvc.GetByName(ctx, name)
	if clusterType.Id == nil {
		return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{}, fmt.Errorf("cluster type '%s' not found in Nautobot", name)
	}
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*clusterType.Id), nil
}

func (s *ClusterSync) buildClusterGroupReference(ctx context.Context, name string) (nb.NullableApprovalWorkflowUser, error) {
	clusterGroup := s.clusterGroupSvc.GetByName(ctx, name)
	if clusterGroup.Id == nil {
		return nb.NullableApprovalWorkflowUser{}, fmt.Errorf("cluster group '%s' not found in Nautobot", name)
	}
	return helpers.BuildNullableApprovalWorkflowUser(*clusterGroup.Id), nil
}

func (s *ClusterSync) buildLocationReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	location := s.locationSvc.GetByName(ctx, name)
	if location.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*location.Id)
}
