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

type ClusterTypeSync struct {
	client         *client.NautobotClient
	clusterTypeSvc *virtualization.ClusterTypeService
}

func NewClusterTypeSync(nautobotClient *client.NautobotClient) *ClusterTypeSync {
	return &ClusterTypeSync{
		client:         nautobotClient.GetClient(),
		clusterTypeSvc: virtualization.NewClusterTypeService(nautobotClient.GetClient()),
	}
}

func (s *ClusterTypeSync) SyncAll(ctx context.Context, data map[string]string) error {
	var clusterTypes models.ClusterTypes
	for key, f := range data {
		var yml []models.ClusterType
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		clusterTypes.ClusterType = append(clusterTypes.ClusterType, yml...)
	}

	for _, ct := range clusterTypes.ClusterType {
		if err := s.syncSingleClusterType(ctx, ct); err != nil {
			return err
		}
	}
	s.deleteObsoleteClusterTypes(ctx, clusterTypes)

	return nil
}

// syncSingleClusterType handles the create/update logic for a single cluster type
func (s *ClusterTypeSync) syncSingleClusterType(ctx context.Context, clusterType models.ClusterType) error {
	existingClusterType := s.clusterTypeSvc.GetByName(ctx, clusterType.Name)

	clusterTypeRequest := nb.ClusterTypeRequest{
		Name:        clusterType.Name,
		Description: nb.PtrString(clusterType.Description),
	}

	if existingClusterType.Id == nil {
		return s.createClusterType(ctx, clusterTypeRequest)
	}

	if !helpers.CompareJSONFields(existingClusterType, clusterTypeRequest) {
		return s.updateClusterType(ctx, *existingClusterType.Id, clusterTypeRequest)
	}

	log.Info("cluster type unchanged, skipping update", "name", clusterTypeRequest.Name)
	return nil
}

// createClusterType creates a new cluster type in Nautobot
func (s *ClusterTypeSync) createClusterType(ctx context.Context, request nb.ClusterTypeRequest) error {
	createdClusterType, err := s.clusterTypeSvc.Create(ctx, request)
	if err != nil || createdClusterType == nil {
		return fmt.Errorf("failed to create cluster type %s: %w", request.Name, err)
	}
	log.Info("cluster type created", "name", request.Name)
	return nil
}

// updateClusterType updates an existing cluster type in Nautobot
func (s *ClusterTypeSync) updateClusterType(ctx context.Context, id string, request nb.ClusterTypeRequest) error {
	updatedClusterType, err := s.clusterTypeSvc.Update(ctx, id, request)
	if err != nil || updatedClusterType == nil {
		return fmt.Errorf("failed to update cluster type %s: %w", request.Name, err)
	}
	log.Info("cluster type updated", "name", request.Name)
	return nil
}

// deleteObsoleteClusterTypes removes cluster types that are not defined in YAML
func (s *ClusterTypeSync) deleteObsoleteClusterTypes(ctx context.Context, clusterTypes models.ClusterTypes) {
	desiredClusterTypes := make(map[string]models.ClusterType)
	for _, clusterType := range clusterTypes.ClusterType {
		desiredClusterTypes[clusterType.Name] = clusterType
	}

	existingClusterTypes := s.clusterTypeSvc.ListAll(ctx)
	existingMap := make(map[string]nb.ClusterType, len(existingClusterTypes))
	for _, clusterType := range existingClusterTypes {
		existingMap[clusterType.Name] = clusterType
	}

	obsoleteClusterTypes := lo.OmitByKeys(existingMap, lo.Keys(desiredClusterTypes))
	for _, clusterType := range obsoleteClusterTypes {
		if clusterType.Id != nil {
			_ = s.clusterTypeSvc.Destroy(ctx, *clusterType.Id)
		}
	}
}
