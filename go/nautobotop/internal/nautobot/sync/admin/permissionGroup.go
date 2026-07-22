package admin

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	adminsvc "github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/admin"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	adminmodels "github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models/admin"
	"go.yaml.in/yaml/v3"
)

type PermissionGroupSync struct {
	client        *client.NautobotClient
	groupSvc      *adminsvc.GroupService
	permissionSvc *adminsvc.PermissionService
}

func NewPermissionGroupSync(nautobotClient *client.NautobotClient) *PermissionGroupSync {
	return &PermissionGroupSync{
		client:        nautobotClient.GetClient(),
		groupSvc:      adminsvc.NewGroupService(nautobotClient),
		permissionSvc: adminsvc.NewPermissionService(nautobotClient),
	}
}

func (s *PermissionGroupSync) SyncAll(ctx context.Context, data map[string]string) error {
	var allPermissions []adminmodels.Permission

	for key, f := range data {
		var config adminmodels.PermissionGroupConfig
		if err := yaml.Unmarshal([]byte(f), &config); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		allPermissions = append(allPermissions, config.Permissions...)
	}

	if len(allPermissions) == 0 {
		log.Info("no permissions to sync")
		return nil
	}

	groupNameToID := make(map[string]int32)

	for _, perm := range allPermissions {
		if err := s.syncSinglePermission(ctx, perm, groupNameToID); err != nil {
			return err
		}
	}

	return nil
}

func (s *PermissionGroupSync) syncSinglePermission(
	ctx context.Context,
	perm adminmodels.Permission,
	groupNameToID map[string]int32,
) error {
	if perm.Name == "" {
		s.client.AddReport("permissionInvalid", "permission has no name, skipping")
		return nil
	}

	actions := perm.BuildActions()
	if len(actions) == 0 {
		s.client.AddReport("permissionInvalid", "permission has no actions, skipping", "name", perm.Name)
		log.Warn("permission has no actions, skipping", "name", perm.Name)
		return nil
	}

	groupIDs := make([]int32, 0, len(perm.Groups))
	for _, groupName := range perm.Groups {
		gid, err := s.resolveGroupID(ctx, groupName, groupNameToID)
		if err != nil {
			return fmt.Errorf("failed to resolve group %q for permission %q: %w", groupName, perm.Name, err)
		}
		groupIDs = append(groupIDs, gid)
	}

	// Parse constraints (nil if empty)
	var constraints interface{}
	if perm.Constraints != "" {
		if err := json.Unmarshal([]byte(perm.Constraints), &constraints); err != nil {
			s.client.AddReport("constraintsInvalid", "invalid JSON constraints", "name", perm.Name, "error", err.Error())
			log.Warn("invalid JSON constraints, skipping constraints", "name", perm.Name, "error", err)
		}
	}

	// Check if the permission already exists
	existing := s.permissionSvc.GetByName(ctx, perm.Name)
	if existing != nil && existing.Id != nil {
		payload := adminsvc.PermissionUpdatePayload{
			Name:        perm.Name,
			Description: perm.Description,
			Enabled:     perm.IsEnabled(),
			Actions:     actions,
			ObjectTypes: perm.ObjectTypes,
			Constraints: constraints, // nil becomes JSON null, clearing it
		}
		for _, gid := range groupIDs {
			payload.Groups = append(payload.Groups, adminsvc.GroupRef{ID: gid})
		}

		if err := s.permissionSvc.Update(ctx, *existing.Id, payload); err != nil {
			return fmt.Errorf("failed to update permission %q: %w", perm.Name, err)
		}
		log.Info("permission synced (updated)", "name", perm.Name, "groups", len(groupIDs))
	} else {
		// Create via SDK
		groupRefs := make([]nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, 0, len(groupIDs))
		for _, gid := range groupIDs {
			id := gid
			groupRefs = append(groupRefs, nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{
				Id: &nb.ApprovalWorkflowApprovalWorkflowDefinitionId{Int32: &id},
			})
		}

		req := nb.ObjectPermissionRequest{
			Name:        perm.Name,
			ObjectTypes: perm.ObjectTypes,
			Actions:     actions,
			Enabled:     nb.PtrBool(perm.IsEnabled()),
			Groups:      groupRefs,
		}
		if perm.Description != "" {
			req.Description = nb.PtrString(perm.Description)
		}
		if constraints != nil {
			req.Constraints = constraints
		}

		created, err := s.permissionSvc.Create(ctx, req)
		if err != nil {
			return fmt.Errorf("failed to create permission %q: %w", perm.Name, err)
		}
		log.Info("permission synced (created)", "name", perm.Name, "id", created.GetId())
	}

	return nil
}

func (s *PermissionGroupSync) resolveGroupID(ctx context.Context, name string, cache map[string]int32) (int32, error) {
	if id, ok := cache[name]; ok {
		return id, nil
	}

	group, err := s.groupSvc.GetOrCreate(ctx, name)
	if err != nil {
		return 0, err
	}
	if group == nil {
		return 0, fmt.Errorf("failed to get or create group: %s", name)
	}

	cache[name] = group.Id
	return group.Id, nil
}
