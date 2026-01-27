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

type LocationSync struct {
	client        *client.NautobotClient
	locationSvc   *dcim.LocationService
	locationTypes *dcim.LocationTypeService
	statusSvc     *dcim.StatusService
}

func NewLocationSync(nautobotClient *client.NautobotClient) *LocationSync {
	return &LocationSync{
		client:        nautobotClient.GetClient(),
		locationSvc:   dcim.NewLocationService(nautobotClient.GetClient()),
		locationTypes: dcim.NewLocationTypeService(nautobotClient.GetClient()),
		statusSvc:     dcim.NewStatusService(nautobotClient.GetClient()),
	}
}

func (s *LocationSync) SyncAll(ctx context.Context, data map[string]string) error {
	var location models.Locations
	for key, f := range data {
		var yml []models.Location
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		location.Location = append(location.Location, yml...)
	}

	for _, l := range location.Location {
		if err := s.syncLocationRecursive(ctx, l, nil); err != nil {
			return err
		}
	}
	s.deleteObsoleteLocations(ctx, location)

	return nil
}

// syncLocationRecursive processes a location  and all its children recursively
func (s *LocationSync) syncLocationRecursive(ctx context.Context, location models.Location, parentID *string) error {
	currentID, err := s.syncSingleLocation(ctx, location, parentID)
	if err != nil {
		return err
	}

	for _, child := range location.Children {
		if err := s.syncLocationRecursive(ctx, child, currentID); err != nil {
			return err
		}
	}

	return nil
}

// syncSingleLocation handles the create/update logic for a single location
func (s *LocationSync) syncSingleLocation(ctx context.Context, location models.Location, parentID *string) (*string, error) {
	existingLocation := s.locationSvc.GetByName(ctx, location.Name)

	locationTypeRequest := nb.LocationRequest{
		Name:         location.Name,
		Description:  nb.PtrString(location.Description),
		Parent:       buildParentReference(parentID),
		LocationType: s.buildLocationTypeReference(ctx, location.LocationType),
		Status:       s.buildStatusReference(ctx, location.Status),
	}

	if existingLocation.Id == nil {
		return s.createLocation(ctx, locationTypeRequest)
	}

	if !helpers.CompareJSONFields(existingLocation, locationTypeRequest) {
		return s.updateLocationType(ctx, *existingLocation.Id, locationTypeRequest)
	}

	log.Info("location  unchanged, skipping update", "name", locationTypeRequest.Name)
	return existingLocation.Id, nil
}

// createLocation creates a new location  in Nautobot
func (s *LocationSync) createLocation(ctx context.Context, request nb.LocationRequest) (*string, error) {
	createdLocationType, err := s.locationSvc.Create(ctx, request)
	if err != nil || createdLocationType == nil {
		return nil, fmt.Errorf("failed to create location  %s: %w", request.Name, err)
	}
	log.Info("location  created", "name", request.Name)
	return createdLocationType.Id, nil
}

// updateLocationType updates an existing location  in Nautobot
func (s *LocationSync) updateLocationType(ctx context.Context, id string, request nb.LocationRequest) (*string, error) {
	updatedLocationType, err := s.locationSvc.Update(ctx, id, request)
	if err != nil || updatedLocationType == nil {
		return nil, fmt.Errorf("failed to update location  %s: %w", request.Name, err)
	}
	log.Info("location  updated", "name", request.Name)
	return updatedLocationType.Id, nil
}

// deleteObsoleteLocations removes location that are not defined in YAML
func (s *LocationSync) deleteObsoleteLocations(ctx context.Context, location models.Locations) {
	desiredLocationTypes := make(map[string]models.Location)
	for _, locationType := range location.Location {
		s.collectAllLocationTypes(locationType, desiredLocationTypes)
	}

	existingLocations := s.locationSvc.ListAll(ctx)
	existingMap := make(map[string]nb.Location, len(existingLocations))
	for _, locationType := range existingLocations {
		existingMap[locationType.Name] = locationType
	}

	obsoleteLocations := lo.OmitByKeys(existingMap, lo.Keys(desiredLocationTypes))
	s.deleteLocationWithDependencies(ctx, obsoleteLocations)
}

// collectAllLocationTypes recursively collects all location including nested children
func (s *LocationSync) collectAllLocationTypes(locationType models.Location, result map[string]models.Location) {
	result[locationType.Name] = locationType
	for _, child := range locationType.Children {
		s.collectAllLocationTypes(child, result)
	}
}

// deleteLocationWithDependencies deletes location in correct order
func (s *LocationSync) deleteLocationWithDependencies(ctx context.Context, obsoleteLocations map[string]nb.Location) {
	idToName := make(map[string]string)
	for name, locationType := range obsoleteLocations {
		if locationType.Id != nil {
			idToName[*locationType.Id] = name
		}
	}

	childrenMap := make(map[string][]string)
	for name, locationType := range obsoleteLocations {
		parentID := s.getParentID(locationType)
		if parentID != "" {
			if parentName, exists := idToName[parentID]; exists {
				childrenMap[parentName] = append(childrenMap[parentName], name)
			}
		}
	}

	deleted := make(map[string]bool)
	for name := range obsoleteLocations {
		s.deleteLocationTypeRecursive(ctx, name, obsoleteLocations, childrenMap, deleted)
	}
}

// deleteLocationTypeRecursive deletes a location  and all its children recursively
func (s *LocationSync) deleteLocationTypeRecursive(ctx context.Context, name string, obsoleteLocations map[string]nb.Location, childrenMap map[string][]string, deleted map[string]bool) {
	if deleted[name] {
		return
	}
	if children, hasChildren := childrenMap[name]; hasChildren {
		for _, childName := range children {
			s.deleteLocationTypeRecursive(ctx, childName, obsoleteLocations, childrenMap, deleted)
		}
	}
	if locationType, exists := obsoleteLocations[name]; exists && locationType.Id != nil {
		_ = s.locationSvc.Destroy(ctx, *locationType.Id)
		deleted[name] = true
	}
}

// getParentID extracts the parent ID from a LocationType
func (s *LocationSync) getParentID(locationType nb.Location) string {
	if locationType.Parent.IsSet() {
		parent := locationType.Parent.Get()
		if parent != nil && parent.Id != nil && parent.Id.String != nil {
			return *parent.Id.String
		}
	}
	return ""
}
func (s *LocationSync) buildStatusReference(ctx context.Context, name string) nb.ApprovalWorkflowStageResponseApprovalWorkflowStage {
	locationType := s.statusSvc.GetByName(ctx, name)
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*locationType.Id)
}

func (s *LocationSync) buildLocationTypeReference(ctx context.Context, name string) nb.ApprovalWorkflowStageResponseApprovalWorkflowStage {
	locationType := s.locationTypes.GetByName(ctx, name)
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*locationType.Id)
}
