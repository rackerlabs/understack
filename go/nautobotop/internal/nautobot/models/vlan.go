package models

type Vlans struct {
	Vlan []Vlan
}

type Vlan struct {
	Name          string   `json:"name" yaml:"name"`
	Vid           int      `json:"vid" yaml:"vid"`
	Status        string   `json:"status" yaml:"status"`
	Role          string   `json:"role" yaml:"role"`
	Description   string   `json:"description" yaml:"description"`
	Locations     []string `json:"locations" yaml:"locations"`
	VlanGroup     string   `json:"vlan_group" yaml:"vlan_group"`
	TenantGroup   string   `json:"tenant_group" yaml:"tenant_group"`
	Tenant        string   `json:"tenant" yaml:"tenant"`
	DynamicGroups []string `json:"dynamic_groups" yaml:"dynamic_groups"`
	Tags          []string `json:"tags" yaml:"tags"`
}
