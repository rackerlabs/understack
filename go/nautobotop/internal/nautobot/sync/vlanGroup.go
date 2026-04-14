package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/ipam"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/samber/lo"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"go.yaml.in/yaml/v3"
)

type VlanGroupSync struct {
	client        *client.NautobotClient
	vlanGroupSvc  *ipam.VlanGroupService
	locationSvc   *dcim.LocationService
	ucvniGroupSvc *ipam.UcvniGroupService
}

func NewVlanGroupSync(nautobotClient *client.NautobotClient) *VlanGroupSync {
	return &VlanGroupSync{
		client:        nautobotClient.GetClient(),
		vlanGroupSvc:  ipam.NewVlanGroupService(nautobotClient),
		locationSvc:   dcim.NewLocationService(nautobotClient.GetClient()),
		ucvniGroupSvc: ipam.NewUcvniGroupService(nautobotClient),
	}
}

func (s *VlanGroupSync) SyncAll(ctx context.Context, data map[string]string) error {
	var vlanGroups models.VlanGroups
	for key, f := range data {
		var yml []models.VlanGroup
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		vlanGroups.VlanGroup = append(vlanGroups.VlanGroup, yml...)
	}

	for _, vg := range vlanGroups.VlanGroup {
		if err := s.syncSingleVlanGroup(ctx, vg); err != nil {
			return err
		}
	}
	s.deleteObsoleteVlanGroups(ctx, vlanGroups)

	return nil
}

// syncSingleVlanGroup handles the create/update logic for a single vlan group
func (s *VlanGroupSync) syncSingleVlanGroup(ctx context.Context, vlanGroup models.VlanGroup) error {
	existingVlanGroup := s.vlanGroupSvc.GetByName(ctx, vlanGroup.Name)

	vlanGroupRequest := nb.VLANGroupRequest{
		Name:     vlanGroup.Name,
		Location: s.buildLocationReference(ctx, vlanGroup.Location),
		Range:    nb.PtrString(vlanGroup.Range),
	}

	if vlanGroup.UcvniGroup != "" {
		ucvniGroup := s.ucvniGroupSvc.GetByName(ctx, vlanGroup.UcvniGroup)
		if ucvniGroup.ID != "" {
			relationships := map[string]nb.ApprovalWorkflowDefinitionRequestRelationshipsValue{
				"ucvnigroup_vlangroup": helpers.BuildRelationshipSource(ucvniGroup.ID),
			}
			vlanGroupRequest.Relationships = &relationships
		} else {
			log.Info("ucvni group not found, skipping relationship", "name", vlanGroup.UcvniGroup)
		}
	}

	if existingVlanGroup.Id == nil {
		return s.createVlanGroup(ctx, vlanGroupRequest)
	}

	if !helpers.CompareJSONFields(existingVlanGroup, vlanGroupRequest) {
		return s.updateVlanGroup(ctx, *existingVlanGroup.Id, vlanGroupRequest)
	}

	log.Info("vlan group unchanged, skipping update", "name", vlanGroupRequest.Name)
	return nil
}

// createVlanGroup creates a new vlan group in Nautobot
func (s *VlanGroupSync) createVlanGroup(ctx context.Context, request nb.VLANGroupRequest) error {
	createdVlanGroup, err := s.vlanGroupSvc.Create(ctx, request)
	if err != nil || createdVlanGroup == nil {
		return fmt.Errorf("failed to create vlan group %s: %w", request.Name, err)
	}
	log.Info("vlan group created", "name", request.Name)
	return nil
}

// updateVlanGroup updates an existing vlan group in Nautobot
func (s *VlanGroupSync) updateVlanGroup(ctx context.Context, id string, request nb.VLANGroupRequest) error {
	updatedVlanGroup, err := s.vlanGroupSvc.Update(ctx, id, request)
	if err != nil || updatedVlanGroup == nil {
		return fmt.Errorf("failed to update vlan group %s: %w", request.Name, err)
	}
	log.Info("vlan group updated", "name", request.Name)
	return nil
}

// deleteObsoleteVlanGroups removes vlan groups that are not defined in YAML
func (s *VlanGroupSync) deleteObsoleteVlanGroups(ctx context.Context, vlanGroups models.VlanGroups) {
	desiredVlanGroups := make(map[string]models.VlanGroup)
	for _, vlanGroup := range vlanGroups.VlanGroup {
		desiredVlanGroups[vlanGroup.Name] = vlanGroup
	}

	existingVlanGroups := s.vlanGroupSvc.ListAll(ctx)
	existingMap := make(map[string]nb.VLANGroup, len(existingVlanGroups))
	for _, vlanGroup := range existingVlanGroups {
		existingMap[vlanGroup.Name] = vlanGroup
	}

	obsoleteVlanGroups := lo.OmitByKeys(existingMap, lo.Keys(desiredVlanGroups))
	for _, vlanGroup := range obsoleteVlanGroups {
		if vlanGroup.Id != nil {
			_ = s.vlanGroupSvc.Destroy(ctx, *vlanGroup.Id)
		}
	}
}

func (s *VlanGroupSync) buildLocationReference(ctx context.Context, name string) nb.NullableApprovalWorkflowUser {
	location := s.locationSvc.GetByName(ctx, name)
	if location.Id == nil {
		return nb.NullableApprovalWorkflowUser{}
	}
	return helpers.BuildNullableApprovalWorkflowUser(*location.Id)
}
