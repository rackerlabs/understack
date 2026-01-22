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

type LocationTypeSync struct {
	client          *client.NautobotClient
	locationTypeSvc *dcim.LocationTypeService
}

func NewLocationTypeSync(nautobotClient *client.NautobotClient) *LocationTypeSync {
	return &LocationTypeSync{
		client:          nautobotClient.GetClient(),
		locationTypeSvc: dcim.NewLocationTypeService(nautobotClient.GetClient()),
	}
}

func (s *LocationTypeSync) SyncAll(ctx context.Context, data map[string]string) error {
	var locationTypes models.LocationTypes
	for key, f := range data {
		var yml []models.LocationType
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		locationTypes.LocationType = append(locationTypes.LocationType, yml...)
	}

	for _, l := range locationTypes.LocationType {
		if err := s.syncLocationTypeRecursive(ctx, l, nil); err != nil {
			return err
		}
	}
	s.deleteObsoleteLocationTypes(ctx, locationTypes)

	return nil
}

// syncLocationTypeRecursive processes a location type and all its children recursively
func (s *LocationTypeSync) syncLocationTypeRecursive(ctx context.Context, locationType models.LocationType, parentID *string) error {
	currentID, err := s.syncSingleLocationType(ctx, locationType, parentID)
	if err != nil {
		return err
	}

	for _, child := range locationType.Children {
		if err := s.syncLocationTypeRecursive(ctx, child, currentID); err != nil {
			return err
		}
	}

	return nil
}

// syncSingleLocationType handles the create/update logic for a single location type
func (s *LocationTypeSync) syncSingleLocationType(ctx context.Context, locationType models.LocationType, parentID *string) (*string, error) {
	existingLocationType := s.locationTypeSvc.GetByName(ctx, locationType.Name)

	locationTypeRequest := nb.LocationTypeRequest{
		ContentTypes: locationType.ContentTypes,
		Name:         locationType.Name,
		Description:  nb.PtrString(locationType.Description),
		Nestable:     nb.PtrBool(locationType.Nestable),
		Parent:       buildParentReference(parentID),
		CustomFields: nil,
	}

	if existingLocationType.Id == nil {
		return s.createLocationType(ctx, locationTypeRequest)
	}

	if !helpers.CompareJSONFields(existingLocationType, locationTypeRequest) {
		return s.updateLocationType(ctx, *existingLocationType.Id, locationTypeRequest)
	}

	log.Info("location type unchanged, skipping update", "name", locationTypeRequest.Name)
	return existingLocationType.Id, nil
}

// createLocationType creates a new location type in Nautobot
func (s *LocationTypeSync) createLocationType(ctx context.Context, request nb.LocationTypeRequest) (*string, error) {
	createdLocationType, err := s.locationTypeSvc.Create(ctx, request)
	if err != nil || createdLocationType == nil {
		return nil, fmt.Errorf("failed to create location type %s: %w", request.Name, err)
	}
	log.Info("location type created", "name", request.Name)
	return createdLocationType.Id, nil
}

// updateLocationType updates an existing location type in Nautobot
func (s *LocationTypeSync) updateLocationType(ctx context.Context, id string, request nb.LocationTypeRequest) (*string, error) {
	updatedLocationType, err := s.locationTypeSvc.Update(ctx, id, request)
	if err != nil || updatedLocationType == nil {
		return nil, fmt.Errorf("failed to update location type %s: %w", request.Name, err)
	}
	log.Info("location type updated", "name", request.Name)
	return updatedLocationType.Id, nil
}

// buildParentReference creates a parent reference for the location type request
func buildParentReference(parentID *string) nb.NullableApprovalWorkflowUser {
	if parentID == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*parentID)
}

// deleteObsoleteLocationTypes removes location types that are not defined in YAML
func (s *LocationTypeSync) deleteObsoleteLocationTypes(ctx context.Context, locationTypes models.LocationTypes) {
	desiredLocationTypes := make(map[string]models.LocationType)
	for _, locationType := range locationTypes.LocationType {
		s.collectAllLocationTypes(locationType, desiredLocationTypes)
	}

	existingLocationTypes := s.locationTypeSvc.ListAll(ctx)
	existingMap := make(map[string]nb.LocationType, len(existingLocationTypes))
	for _, locationType := range existingLocationTypes {
		existingMap[locationType.Name] = locationType
	}

	obsoleteLocationTypes := lo.OmitByKeys(existingMap, lo.Keys(desiredLocationTypes))
	s.deleteLocationTypesWithDependencies(ctx, obsoleteLocationTypes)
}

// collectAllLocationTypes recursively collects all location types including nested children
func (s *LocationTypeSync) collectAllLocationTypes(locationType models.LocationType, result map[string]models.LocationType) {
	result[locationType.Name] = locationType
	for _, child := range locationType.Children {
		s.collectAllLocationTypes(child, result)
	}
}

// deleteLocationTypesWithDependencies deletes location types in correct order
func (s *LocationTypeSync) deleteLocationTypesWithDependencies(ctx context.Context, obsoleteLocationTypes map[string]nb.LocationType) {
	idToName := make(map[string]string)
	for name, locationType := range obsoleteLocationTypes {
		if locationType.Id != nil {
			idToName[*locationType.Id] = name
		}
	}

	childrenMap := make(map[string][]string)
	for name, locationType := range obsoleteLocationTypes {
		parentID := s.getParentID(locationType)
		if parentID != "" {
			if parentName, exists := idToName[parentID]; exists {
				childrenMap[parentName] = append(childrenMap[parentName], name)
			}
		}
	}

	deleted := make(map[string]bool)
	for name := range obsoleteLocationTypes {
		s.deleteLocationTypeRecursive(ctx, name, obsoleteLocationTypes, childrenMap, deleted)
	}
}

// deleteLocationTypeRecursive deletes a location type and all its children recursively
func (s *LocationTypeSync) deleteLocationTypeRecursive(ctx context.Context, name string, obsoleteLocationTypes map[string]nb.LocationType, childrenMap map[string][]string, deleted map[string]bool) {
	if deleted[name] {
		return
	}
	if children, hasChildren := childrenMap[name]; hasChildren {
		for _, childName := range children {
			s.deleteLocationTypeRecursive(ctx, childName, obsoleteLocationTypes, childrenMap, deleted)
		}
	}
	if locationType, exists := obsoleteLocationTypes[name]; exists && locationType.Id != nil {
		_ = s.locationTypeSvc.Destroy(ctx, *locationType.Id)
		deleted[name] = true
	}
}

// getParentID extracts the parent ID from a LocationType
func (s *LocationTypeSync) getParentID(locationType nb.LocationType) string {
	if locationType.Parent.IsSet() {
		parent := locationType.Parent.Get()
		if parent != nil && parent.Id != nil && parent.Id.String != nil {
			return *parent.Id.String
		}
	}
	return ""
}
