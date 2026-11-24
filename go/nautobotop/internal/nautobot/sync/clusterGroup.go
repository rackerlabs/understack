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

	return s.applyClusterGroups(ctx, clusterGroups, s.syncSingleClusterGroup, s.deleteObsoleteClusterGroups)
}

// applyClusterGroups contains the orchestration for a parsed set of cluster groups:
// apply each one (isolating per-item data errors), prune obsolete cluster groups,
// and report any data failures. syncOne and prune are parameters so the
// orchestration can be exercised in tests without a live Nautobot.
func (s *ClusterGroupSync) applyClusterGroups(
	ctx context.Context,
	clusterGroups models.ClusterGroups,
	syncOne func(context.Context, models.ClusterGroup) error,
	prune func(context.Context, models.ClusterGroups),
) error {
	// Apply every cluster group, isolating per-item data errors so one bad
	// group does not block the rest. Infrastructure errors still abort.
	result, err := syncItems(ctx, clusterGroups.ClusterGroup, syncOne)
	if err != nil {
		return err
	}

	prune(ctx, clusterGroups)

	if result.HasFailures() {
		for _, f := range result.DataFailures {
			s.client.AddReport("clusterGroupDataError", f.Err.Error())
		}
		return &PartialSyncError{Resource: "clusterGroup", Failures: result.DataFailures}
	}

	return nil
}

// syncSingleClusterGroup handles the create/update logic for a single cluster group
func (s *ClusterGroupSync) syncSingleClusterGroup(ctx context.Context, clusterGroup models.ClusterGroup) error {
	existingClusterGroup := s.clusterGroupSvc.GetByID(ctx, clusterGroup.ID)

	clusterGroupRequest := nb.ClusterGroupRequest{
		Id:          optionalID(clusterGroup.ID),
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
