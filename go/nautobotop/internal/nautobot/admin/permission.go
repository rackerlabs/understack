package admin

import (
	"context"
	"net/http"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type PermissionService struct {
	client *client.NautobotClient
}

func NewPermissionService(nautobotClient *client.NautobotClient) *PermissionService {
	return &PermissionService{
		client: nautobotClient,
	}
}

func (s *PermissionService) Create(ctx context.Context, req nb.ObjectPermissionRequest) (*nb.ObjectPermission, error) {
	perm, resp, err := s.client.APIClient.UsersAPI.UsersPermissionsCreate(ctx).ObjectPermissionRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewPermission", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreatePermission", "created permission", perm.Name)
	return perm, nil
}

func (s *PermissionService) GetByName(ctx context.Context, name string) *nb.ObjectPermission {
	list, resp, err := s.client.APIClient.UsersAPI.UsersPermissionsList(ctx).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetPermissionByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nil
	}
	if list == nil || len(list.Results) == 0 {
		return nil
	}
	return &list.Results[0]
}

func (s *PermissionService) GetByID(ctx context.Context, id string) *nb.ObjectPermission {
	if id == "" {
		return nil
	}
	list, resp, err := s.client.APIClient.UsersAPI.UsersPermissionsList(ctx).Id([]string{id}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetPermissionByID", "failed to get", "id", id, "error", err.Error(), "response_body", bodyString)
		return nil
	}
	if list == nil || len(list.Results) == 0 {
		return nil
	}
	return &list.Results[0]
}

func (s *PermissionService) ListAll(ctx context.Context) []nb.ObjectPermission {
	return helpers.PaginatedList(
		ctx,
		func(ctx context.Context, limit, offset int32) ([]nb.ObjectPermission, int32, *http.Response, error) {
			list, resp, err := s.client.APIClient.UsersAPI.UsersPermissionsList(ctx).
				Limit(limit).
				Offset(offset).
				Execute()
			if err != nil {
				return nil, 0, resp, err
			}
			if list == nil {
				return nil, 0, resp, nil
			}
			return list.Results, list.Count, resp, nil
		},
		s.client.AddReport,
		"ListAllPermissions",
	)
}

// PermissionUpdatePayload represents the desired state of a permission.
type PermissionUpdatePayload struct {
	Name        string      `json:"name"`
	Description string      `json:"description"`
	Enabled     bool        `json:"enabled"`
	Actions     interface{} `json:"actions"`
	ObjectTypes []string    `json:"object_types"`
	Constraints interface{} `json:"constraints"`
	Groups      []GroupRef  `json:"groups"`
}

// GroupRef is a minimal group reference for the permission update payload.
type GroupRef struct {
	ID int32 `json:"id"`
}

// Update performs a full PUT via the SDK client
func (s *PermissionService) Update(ctx context.Context, id string, payload PermissionUpdatePayload) error {
	// Build the SDK request
	req := *nb.NewObjectPermissionRequest(payload.ObjectTypes, payload.Name, payload.Actions)
	req.Enabled = nb.PtrBool(payload.Enabled)
	if payload.Description != "" {
		req.Description = nb.PtrString(payload.Description)
	}

	// Set groups
	groups := make([]nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, 0, len(payload.Groups))
	for _, g := range payload.Groups {
		gid := g.ID
		groups = append(groups, nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{
			Id: &nb.ApprovalWorkflowApprovalWorkflowDefinitionId{Int32: &gid},
		})
	}
	req.Groups = groups

	if payload.Constraints != nil {
		req.Constraints = payload.Constraints
	} else {
		req.AdditionalProperties = map[string]interface{}{
			"constraints": nil,
		}
	}

	perm, resp, err := s.client.APIClient.UsersAPI.UsersPermissionsUpdate(ctx, id).ObjectPermissionRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdatePermission", "failed to update", "id", id, "model", payload.Name, "error", err.Error(), "response_body", bodyString)
		return err
	}
	log.Info("successfully updated permission", "id", id, "model", perm.GetName())
	return nil
}

func (s *PermissionService) Destroy(ctx context.Context, id string) error {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("DestroyPermission", "failed to check ownership", "id", id, "error", err.Error())
		return err
	}
	if !owned {
		log.Warn("skipping destroy, object not created by user", "id", id, "user", s.client.Username)
		return nil
	}

	resp, err := s.client.APIClient.UsersAPI.UsersPermissionsDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyPermission", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	return nil
}
