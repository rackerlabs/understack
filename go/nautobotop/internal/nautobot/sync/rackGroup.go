package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/samber/lo"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"go.yaml.in/yaml/v3"
)

type RackGroupSync struct {
	client       *client.NautobotClient
	rackGroupSvc *dcim.RackGroupService
	locationSvc  *dcim.LocationService
}

func NewRackGroupSync(nautobotClient *client.NautobotClient) *RackGroupSync {
	return &RackGroupSync{
		client:       nautobotClient.GetClient(),
		rackGroupSvc: dcim.NewRackGroupService(nautobotClient),
		locationSvc:  dcim.NewLocationService(nautobotClient.GetClient()),
	}
}

func (s *RackGroupSync) SyncAll(ctx context.Context, data map[string]string) error {
	var rackGroups models.RackGroups
	for key, f := range data {
		var yml []models.RackGroup
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		rackGroups.RackGroup = append(rackGroups.RackGroup, yml...)
	}

	for _, l := range rackGroups.RackGroup {
		if err := s.syncLocationRecursive(ctx, l, nil); err != nil {
			return err
		}
	}
	s.deleteObsoleteRackGroup(ctx, rackGroups)

	return nil
}

// syncLocationRecursive processes a location  and all its children recursively
func (s *RackGroupSync) syncLocationRecursive(ctx context.Context, rackGroup models.RackGroup, parentID *string) error {
	currentID, err := s.syncSingleRackGroup(ctx, rackGroup, parentID)
	if err != nil {
		return err
	}

	for _, child := range rackGroup.Children {
		if err := s.syncLocationRecursive(ctx, child, currentID); err != nil {
			return err
		}
	}

	return nil
}

// syncSingleRackGroup handles the create/update logic for a single location
func (s *RackGroupSync) syncSingleRackGroup(ctx context.Context, rackGroup models.RackGroup, parentID *string) (*string, error) {
	existingRackGroup := s.rackGroupSvc.GetByName(ctx, rackGroup.Name)

	rackGroupRequest := nb.RackGroupRequest{
		Name:        rackGroup.Name,
		Description: nb.PtrString(rackGroup.Description),
		Parent:      buildParentReference(parentID),
		Location:    s.buildLocationReference(ctx, rackGroup.Location),
	}

	if existingRackGroup.Id == nil {
		return s.createRackGroup(ctx, rackGroupRequest)
	}

	if !helpers.CompareJSONFields(existingRackGroup, rackGroupRequest) {
		return s.updateRackGroup(ctx, *existingRackGroup.Id, rackGroupRequest)
	}

	log.Info("location  unchanged, skipping update", "name", rackGroupRequest.Name)
	return rackGroupRequest.Id, nil
}

// createRackGroup creates a new location  in Nautobot
func (s *RackGroupSync) createRackGroup(ctx context.Context, request nb.RackGroupRequest) (*string, error) {
	createdRackGroup, err := s.rackGroupSvc.Create(ctx, request)
	if err != nil || createdRackGroup == nil {
		return nil, fmt.Errorf("failed to create rackgroup  %s: %w", request.Name, err)
	}
	log.Info("location  created", "name", request.Name)
	return createdRackGroup.Id, nil
}

// updateRackGroup updates an existing location  in Nautobot
func (s *RackGroupSync) updateRackGroup(ctx context.Context, id string, request nb.RackGroupRequest) (*string, error) {
	updatedRackGroup, err := s.rackGroupSvc.Update(ctx, id, request)
	if err != nil || updatedRackGroup == nil {
		return nil, fmt.Errorf("failed to update location  %s: %w", request.Name, err)
	}
	log.Info("location  updated", "name", request.Name)
	return updatedRackGroup.Id, nil
}

// deleteObsoleteRackGroup removes location that are not defined in YAML
func (s *RackGroupSync) deleteObsoleteRackGroup(ctx context.Context, rackGroups models.RackGroups) {
	desiredRackGroups := make(map[string]models.RackGroup)
	for _, rackGroup := range rackGroups.RackGroup {
		s.collectAllRackGroups(rackGroup, desiredRackGroups)
	}

	existingRackGroup := s.rackGroupSvc.ListAll(ctx)
	existingMap := make(map[string]nb.RackGroup, len(existingRackGroup))
	for _, rackGroup := range existingRackGroup {
		existingMap[rackGroup.Name] = rackGroup
	}

	obsoleteRackGroup := lo.OmitByKeys(existingMap, lo.Keys(desiredRackGroups))
	s.deleteLocationWithDependencies(ctx, obsoleteRackGroup)
}

// collectAllRackGroups recursively collects all location including nested children
func (s *RackGroupSync) collectAllRackGroups(rackGroup models.RackGroup, result map[string]models.RackGroup) {
	result[rackGroup.Name] = rackGroup
	for _, child := range rackGroup.Children {
		s.collectAllRackGroups(child, result)
	}
}

// deleteLocationWithDependencies deletes location in correct order
func (s *RackGroupSync) deleteLocationWithDependencies(ctx context.Context, obsoleteRackGroup map[string]nb.RackGroup) {
	idToName := make(map[string]string)
	for name, rackGroup := range obsoleteRackGroup {
		if rackGroup.Id != nil {
			idToName[*rackGroup.Id] = name
		}
	}

	childrenMap := make(map[string][]string)
	for name, rackGroup := range obsoleteRackGroup {
		parentID := s.getParentID(rackGroup)
		if parentID != "" {
			if parentName, exists := idToName[parentID]; exists {
				childrenMap[parentName] = append(childrenMap[parentName], name)
			}
		}
	}

	deleted := make(map[string]bool)
	for name := range obsoleteRackGroup {
		s.deleteRackGroupRecursive(ctx, name, obsoleteRackGroup, childrenMap, deleted)
	}
}

// deleteRackGroupRecursive deletes a location  and all its children recursively
func (s *RackGroupSync) deleteRackGroupRecursive(ctx context.Context, name string, obsoleteRackGroup map[string]nb.RackGroup, childrenMap map[string][]string, deleted map[string]bool) {
	if deleted[name] {
		return
	}
	if children, hasChildren := childrenMap[name]; hasChildren {
		for _, childName := range children {
			s.deleteRackGroupRecursive(ctx, childName, obsoleteRackGroup, childrenMap, deleted)
		}
	}
	if rackGroup, exists := obsoleteRackGroup[name]; exists && rackGroup.Id != nil {
		_ = s.rackGroupSvc.Destroy(ctx, *rackGroup.Id)
		deleted[name] = true
	}
}

// getParentID extracts the parent ID from a RackGroup
func (s *RackGroupSync) getParentID(rackGroup nb.RackGroup) string {
	if rackGroup.Parent.IsSet() {
		parent := rackGroup.Parent.Get()
		if parent != nil && parent.Id != nil && parent.Id.String != nil {
			return *parent.Id.String
		}
	}
	return ""
}

func (s *RackGroupSync) buildLocationReference(ctx context.Context, name string) nb.ApprovalWorkflowStageResponseApprovalWorkflowStage {
	rackGroup := s.locationSvc.GetByName(ctx, name)
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*rackGroup.Id)
}
