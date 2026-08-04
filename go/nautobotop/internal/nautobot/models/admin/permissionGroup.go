package admin

// Permission represents a single Nautobot ObjectPermission with its group assignments.
type Permission struct {
	Name              string   `json:"name" yaml:"name"`
	Description       string   `json:"description" yaml:"description"`
	Enabled           *bool    `json:"enabled" yaml:"enabled"`
	CanView           bool     `json:"can_view" yaml:"can_view"`
	CanAdd            bool     `json:"can_add" yaml:"can_add"`
	CanChange         bool     `json:"can_change" yaml:"can_change"`
	CanDelete         bool     `json:"can_delete" yaml:"can_delete"`
	AdditionalActions []string `json:"additional_actions" yaml:"additional_actions"`
	ObjectTypes       []string `json:"object_types" yaml:"object_types"`
	Groups            []string `json:"groups" yaml:"groups"`
	Constraints       string   `json:"constraints" yaml:"constraints"`
}

// PermissionGroupConfig represents the top-level structure for the permissions configmap.
type PermissionGroupConfig struct {
	Permissions []Permission `json:"permissions" yaml:"permissions"`
}

// BuildActions constructs the actions list from the boolean flags and additional actions.
func (p *Permission) BuildActions() []string {
	var actions []string
	if p.CanView {
		actions = append(actions, "view")
	}
	if p.CanAdd {
		actions = append(actions, "add")
	}
	if p.CanChange {
		actions = append(actions, "change")
	}
	if p.CanDelete {
		actions = append(actions, "delete")
	}
	actions = append(actions, p.AdditionalActions...)
	return actions
}

// IsEnabled returns whether the permission is enabled (defaults to true if not set).
func (p *Permission) IsEnabled() bool {
	if p.Enabled == nil {
		return true
	}
	return *p.Enabled
}
