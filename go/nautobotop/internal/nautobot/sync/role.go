package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/extras"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/samber/lo"
	"go.yaml.in/yaml/v3"
)

type RoleSync struct {
	client  *client.NautobotClient
	roleSvc *extras.RoleService
}

func NewRoleSync(nautobotClient *client.NautobotClient) *RoleSync {
	return &RoleSync{
		client:  nautobotClient.GetClient(),
		roleSvc: extras.NewRoleService(nautobotClient),
	}
}

func (s *RoleSync) SyncAll(ctx context.Context, data map[string]string) error {
	var roles models.Roles
	for key, f := range data {
		var yml []models.Role
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		roles.Role = append(roles.Role, yml...)
	}

	for _, role := range roles.Role {
		if err := s.syncSingleRole(ctx, role); err != nil {
			return err
		}
	}
	s.deleteObsoleteRoles(ctx, roles)
	return nil
}

func (s *RoleSync) syncSingleRole(ctx context.Context, role models.Role) error {
	existing := s.roleSvc.GetByName(ctx, role.Name)

	roleRequest := nb.RoleRequest{
		Name:         role.Name,
		ContentTypes: role.ContentTypes,
	}
	if role.Description != "" {
		roleRequest.Description = nb.PtrString(role.Description)
	}
	if role.Color != "" {
		roleRequest.Color = nb.PtrString(role.Color)
	}
	if role.Weight > 0 {
		roleRequest.Weight = *nb.NewNullableInt32(nb.PtrInt32(int32(role.Weight)))
	}

	if existing.Id == nil {
		return s.createRole(ctx, roleRequest)
	}
	if !helpers.CompareJSONFields(existing, roleRequest) {
		return s.updateRole(ctx, *existing.Id, roleRequest)
	}
	log.Info("role unchanged, skipping update", "name", roleRequest.Name)
	return nil
}

func (s *RoleSync) createRole(ctx context.Context, request nb.RoleRequest) error {
	created, err := s.roleSvc.Create(ctx, request)
	if err != nil || created == nil {
		return fmt.Errorf("failed to create role %s: %w", request.Name, err)
	}
	log.Info("role created", "name", request.Name)
	return nil
}

func (s *RoleSync) updateRole(ctx context.Context, id string, request nb.RoleRequest) error {
	updated, err := s.roleSvc.Update(ctx, id, request)
	if err != nil || updated == nil {
		return fmt.Errorf("failed to update role %s: %w", request.Name, err)
	}
	log.Info("role updated", "name", request.Name)
	return nil
}

func (s *RoleSync) deleteObsoleteRoles(ctx context.Context, roles models.Roles) {
	desired := make(map[string]models.Role)
	for _, role := range roles.Role {
		desired[role.Name] = role
	}

	existing := s.roleSvc.ListAll(ctx)
	existingMap := make(map[string]nb.Role, len(existing))
	for _, role := range existing {
		existingMap[role.Name] = role
	}

	obsolete := lo.OmitByKeys(existingMap, lo.Keys(desired))
	for _, role := range obsolete {
		if role.Id != nil {
			_ = s.roleSvc.Destroy(ctx, *role.Id)
		}
	}
}
