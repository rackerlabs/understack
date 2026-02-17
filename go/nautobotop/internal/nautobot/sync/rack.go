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

type RackSync struct {
	client       *client.NautobotClient
	rackSvc      *dcim.RackService
	locationSvc  *dcim.LocationService
	rackGroupSvc *dcim.RackGroupService
	statusSvc    *dcim.StatusService
}

func NewRackSync(nautobotClient *client.NautobotClient) *RackSync {
	return &RackSync{
		client:       nautobotClient.GetClient(),
		rackSvc:      dcim.NewRackService(nautobotClient),
		locationSvc:  dcim.NewLocationService(nautobotClient.GetClient()),
		rackGroupSvc: dcim.NewRackGroupService(nautobotClient),
		statusSvc:    dcim.NewStatusService(nautobotClient.GetClient()),
	}
}

func (s *RackSync) SyncAll(ctx context.Context, data map[string]string) error {
	var racks models.Racks
	for key, f := range data {
		var yml []models.Rack
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		racks.Rack = append(racks.Rack, yml...)
	}

	for _, rack := range racks.Rack {
		if err := s.syncSingleRack(ctx, rack); err != nil {
			return err
		}
	}
	s.deleteObsoleteRacks(ctx, racks)

	return nil
}

// syncSingleRack handles the create/update logic for a single rack
func (s *RackSync) syncSingleRack(ctx context.Context, rack models.Rack) error {
	existingRack := s.rackSvc.GetByName(ctx, rack.Name)

	// Build location reference
	locationRef, err := s.buildLocationReference(ctx, rack.Location)
	if err != nil {
		return fmt.Errorf("failed to build location reference for rack %s: %w", rack.Name, err)
	}

	// Build status reference
	statusRef, err := s.buildStatusReference(ctx, rack.Status)
	if err != nil {
		return fmt.Errorf("failed to build status reference for rack %s: %w", rack.Name, err)
	}

	rackRequest := nb.WritableRackRequest{
		Name:     rack.Name,
		Comments: nb.PtrString(rack.Description),
		Location: locationRef,
		Status:   statusRef,
		UHeight:  nb.PtrInt32(int32(rack.UHeight)),
	}

	if rack.Facility != "" {
		rackRequest.FacilityId = *nb.NewNullableString(nb.PtrString(rack.Facility))
	}

	if rack.RackGroup != "" {
		rackGroupRef, err := s.buildRackGroupReference(ctx, rack.RackGroup)
		if err != nil {
			return fmt.Errorf("failed to build rack group reference for rack %s: %w", rack.Name, err)
		}
		rackRequest.RackGroup = rackGroupRef
	}

	if existingRack.Id == nil {
		return s.createRack(ctx, rackRequest)
	}

	if !helpers.CompareJSONFields(existingRack, rackRequest) {
		return s.updateRack(ctx, *existingRack.Id, rackRequest)
	}

	log.Info("rack unchanged, skipping update", "name", rackRequest.Name)
	return nil
}

// createRack creates a new rack in Nautobot
func (s *RackSync) createRack(ctx context.Context, request nb.WritableRackRequest) error {
	createdRack, err := s.rackSvc.Create(ctx, request)
	if err != nil || createdRack == nil {
		return fmt.Errorf("failed to create rack %s: %w", request.Name, err)
	}
	log.Info("rack created", "name", request.Name)
	return nil
}

// updateRack updates an existing rack in Nautobot
func (s *RackSync) updateRack(ctx context.Context, id string, request nb.WritableRackRequest) error {
	updatedRack, err := s.rackSvc.Update(ctx, id, request)
	if err != nil || updatedRack == nil {
		return fmt.Errorf("failed to update rack %s: %w", request.Name, err)
	}
	log.Info("rack updated", "name", request.Name)
	return nil
}

// deleteObsoleteRacks removes racks that are not defined in YAML
func (s *RackSync) deleteObsoleteRacks(ctx context.Context, racks models.Racks) {
	desiredRacks := make(map[string]models.Rack)
	for _, rack := range racks.Rack {
		desiredRacks[rack.Name] = rack
	}

	existingRacks := s.rackSvc.ListAll(ctx)
	existingMap := make(map[string]nb.Rack, len(existingRacks))
	for _, rack := range existingRacks {
		existingMap[rack.Name] = rack
	}

	obsoleteRacks := lo.OmitByKeys(existingMap, lo.Keys(desiredRacks))
	for _, obsoleteRack := range obsoleteRacks {
		if obsoleteRack.Id != nil {
			err := s.rackSvc.Destroy(ctx, *obsoleteRack.Id)
			if err != nil {
				log.Error("failed to delete obsolete rack", "name", obsoleteRack.Name)
			}
		}
	}
}

func (s *RackSync) buildLocationReference(ctx context.Context, name string) (nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	location := s.locationSvc.GetByName(ctx, name)
	if location.Id == nil {
		return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{}, fmt.Errorf("location '%s' not found in Nautobot", name)
	}
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*location.Id), nil
}

func (s *RackSync) buildRackGroupReference(ctx context.Context, name string) (nb.NullableBulkWritableRackRequestRackGroup, error) {
	rackGroup := s.rackGroupSvc.GetByName(ctx, name)
	if rackGroup.Id == nil {
		return nb.NullableBulkWritableRackRequestRackGroup{}, fmt.Errorf("rack group '%s' not found in Nautobot", name)
	}
	return helpers.BuildNullableBulkWritableRackRequestRackGroup(*rackGroup.Id), nil
}

func (s *RackSync) buildStatusReference(ctx context.Context, name string) (nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	status := s.statusSvc.GetByName(ctx, name)
	if status.Id == nil {
		return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{}, fmt.Errorf("status '%s' not found in Nautobot", name)
	}
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*status.Id), nil
}
