package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/virtualization"
	"github.com/samber/lo"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"go.yaml.in/yaml/v3"
)

type ClusterGroupSync struct {
	client          *client.NautobotClient
	clusterGroupSvc *virtualization.ClusterGroupService
}

func NewClusterGroupSync(nautobotClient *client.NautobotClient) *ClusterGroupSync {
	return &ClusterGroupSync{
		client:          nautobotClient.GetClient(),
		clusterGroupSvc: virtualization.NewClusterGroupService(nautobotClient.GetClient()),
	}
}

func (s *ClusterGroupSync) SyncAll(ctx context.Context, data map[string]string) error {
	var clusterGroups models.ClusterGroups
	for key, f := range data {
		var yml []models.ClusterGroup
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		clusterGroups.ClusterGroup = append(clusterGroups.ClusterGroup, yml...)
	}

	for _, cg := range clusterGroups.ClusterGroup {
		if err := s.syncSingleClusterGroup(ctx, cg); err != nil {
			return err
		}
	}
	s.deleteObsoleteClusterGroups(ctx, clusterGroups)

	return nil
}

// syncSingleClusterGroup handles the create/update logic for a single cluster group
func (s *ClusterGroupSync) syncSingleClusterGroup(ctx context.Context, clusterGroup models.ClusterGroup) error {
	existingClusterGroup := s.clusterGroupSvc.GetByName(ctx, clusterGroup.Name)

	clusterGroupRequest := nb.ClusterGroupRequest{
		Name:        clusterGroup.Name,
		Description: nb.PtrString(clusterGroup.Description),
	}

	if existingClusterGroup.Id == nil {
		return s.createClusterGroup(ctx, clusterGroupRequest)
	}

	if !helpers.CompareJSONFields(existingClusterGroup, clusterGroupRequest) {
		return s.updateClusterGroup(ctx, *existingClusterGroup.Id, clusterGroupRequest)
	}

	log.Info("cluster group unchanged, skipping update", "name", clusterGroupRequest.Name)
	return nil
}

// createClusterGroup creates a new cluster group in Nautobot
func (s *ClusterGroupSync) createClusterGroup(ctx context.Context, request nb.ClusterGroupRequest) error {
	createdClusterGroup, err := s.clusterGroupSvc.Create(ctx, request)
	if err != nil || createdClusterGroup == nil {
		return fmt.Errorf("failed to create cluster group %s: %w", request.Name, err)
	}
	log.Info("cluster group created", "name", request.Name)
	return nil
}

// updateClusterGroup updates an existing cluster group in Nautobot
func (s *ClusterGroupSync) updateClusterGroup(ctx context.Context, id string, request nb.ClusterGroupRequest) error {
	updatedClusterGroup, err := s.clusterGroupSvc.Update(ctx, id, request)
	if err != nil || updatedClusterGroup == nil {
		return fmt.Errorf("failed to update cluster group %s: %w", request.Name, err)
	}
	log.Info("cluster group updated", "name", request.Name)
	return nil
}

// deleteObsoleteClusterGroups removes cluster groups that are not defined in YAML
func (s *ClusterGroupSync) deleteObsoleteClusterGroups(ctx context.Context, clusterGroups models.ClusterGroups) {
	desiredClusterGroups := make(map[string]models.ClusterGroup)
	for _, clusterGroup := range clusterGroups.ClusterGroup {
		desiredClusterGroups[clusterGroup.Name] = clusterGroup
	}

	existingClusterGroups := s.clusterGroupSvc.ListAll(ctx)
	existingMap := make(map[string]nb.ClusterGroup, len(existingClusterGroups))
	for _, clusterGroup := range existingClusterGroups {
		existingMap[clusterGroup.Name] = clusterGroup
	}

	obsoleteClusterGroups := lo.OmitByKeys(existingMap, lo.Keys(desiredClusterGroups))
	for _, clusterGroup := range obsoleteClusterGroups {
		if clusterGroup.Id != nil {
			_ = s.clusterGroupSvc.Destroy(ctx, *clusterGroup.Id)
		}
	}
}
