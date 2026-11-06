package sync

import (
	"context"
	"errors"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
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

	return s.applyRackGroups(ctx, rackGroups, s.syncSingleRackGroup, s.deleteObsoleteRackGroup)
}

// applyRackGroups contains the orchestration for a parsed rack group tree:
// apply each root and its children (isolating per-item data errors), prune
// obsolete groups, and report any data failures. syncOne and prune are
// parameters so the orchestration can be exercised in tests without a live
// Nautobot.
func (s *RackGroupSync) applyRackGroups(
	ctx context.Context,
	rackGroups models.RackGroups,
	syncOne func(context.Context, models.RackGroup, *string) (*string, error),
	prune func(context.Context, models.RackGroups),
) error {
	var failures []ItemFailure
	for _, rg := range rackGroups.RackGroup {
		nodeFailures, err := s.syncRackGroupTreeNode(ctx, rg, nil, syncOne)
		if err != nil {
			// Infrastructure error: stop immediately; prune does not run.
			return err
		}
		failures = append(failures, nodeFailures...)
	}

	// Prune obsolete rack groups after the apply loop.
	prune(ctx, rackGroups)

	if len(failures) > 0 {
		for _, f := range failures {
			s.client.AddReport("rackGroupDataError", f.Err.Error())
		}
		return &PartialSyncError{Resource: "rackGroup", Failures: failures}
	}

	return nil
}

// syncRackGroupTreeNode syncs one rack group node and then recurses into its
// children. If the node itself fails with a data error its entire subtree is
// skipped (child IDs depend on the parent being present) and the failure is
// collected. An infrastructure error propagates immediately.
func (s *RackGroupSync) syncRackGroupTreeNode(
	ctx context.Context,
	rackGroup models.RackGroup,
	parentID *string,
	syncOne func(context.Context, models.RackGroup, *string) (*string, error),
) ([]ItemFailure, error) {
	currentID, err := syncOne(ctx, rackGroup, parentID)
	if err != nil {
		var de *syncerr.DataError
		if errors.As(err, &de) {
			return []ItemFailure{{Item: de.Item, Err: err}}, nil
		}
		return nil, err
	}

	var failures []ItemFailure
	for _, child := range rackGroup.Children {
		childFailures, err := s.syncRackGroupTreeNode(ctx, child, currentID, syncOne)
		if err != nil {
			return failures, err
		}
		failures = append(failures, childFailures...)
	}
	return failures, nil
}

// syncSingleRackGroup handles the create/update logic for a single location
func (s *RackGroupSync) syncSingleRackGroup(ctx context.Context, rackGroup models.RackGroup, parentID *string) (*string, error) {
	existingRackGroup := s.rackGroupSvc.GetByID(ctx, rackGroup.ID)

	rackGroupRequest := nb.RackGroupRequest{
		Id:          optionalID(rackGroup.ID),
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

	log.Info("rackGroup is unchanged, skipping update", "name", rackGroupRequest.Name)
	return existingRackGroup.Id, nil
}

// createRackGroup creates a new location  in Nautobot
func (s *RackGroupSync) createRackGroup(ctx context.Context, request nb.RackGroupRequest) (*string, error) {
	createdRackGroup, err := s.rackGroupSvc.Create(ctx, request)
	if err != nil || createdRackGroup == nil {
		return nil, fmt.Errorf("failed to create rackgroup  %s: %w", request.Name, err)
	}
	log.Info("rackGroup created", "name", request.Name)
	return createdRackGroup.Id, nil
}

// updateRackGroup updates an existing location  in Nautobot
func (s *RackGroupSync) updateRackGroup(ctx context.Context, id string, request nb.RackGroupRequest) (*string, error) {
	updatedRackGroup, err := s.rackGroupSvc.Update(ctx, id, request)
	if err != nil || updatedRackGroup == nil {
		return nil, fmt.Errorf("failed to update rackGroup  %s: %w", request.Name, err)
	}
	log.Info("rackGroup  updated", "name", request.Name)
	return updatedRackGroup.Id, nil
}

// deleteObsoleteRackGroup removes rackGroup that are not defined in YAML
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
	s.deleteRackGroupWithDependencies(ctx, obsoleteRackGroup)
}

// collectAllRackGroups recursively collects all rackGroups including nested children
func (s *RackGroupSync) collectAllRackGroups(rackGroup models.RackGroup, result map[string]models.RackGroup) {
	result[rackGroup.Name] = rackGroup
	for _, child := range rackGroup.Children {
		s.collectAllRackGroups(child, result)
	}
}

// deleteRackGroupWithDependencies deletes rackGroups in correct order
func (s *RackGroupSync) deleteRackGroupWithDependencies(ctx context.Context, obsoleteRackGroup map[string]nb.RackGroup) {
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

// deleteRackGroupRecursive deletes a rackGroup  and all its children recursively
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
