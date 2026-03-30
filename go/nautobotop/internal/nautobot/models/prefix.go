package models

type Prefixes struct {
	Prefix []Prefix
}

type Prefix struct {
	Prefix        string   `json:"prefix" yaml:"prefix"`
	Namespace     string   `json:"namespace" yaml:"namespace"`
	Type          string   `json:"type" yaml:"type"`
	Status        string   `json:"status" yaml:"status"`
	Role          string   `json:"role" yaml:"role"`
	Rir           string   `json:"rir" yaml:"rir"`
	DateAllocated string   `json:"date_allocated" yaml:"date_allocated"`
	Description   string   `json:"description" yaml:"description"`
	Vrfs          []string `json:"vrfs" yaml:"vrfs"`
	Locations     []string `json:"locations" yaml:"locations"`
	VlanGroup     string   `json:"vlan_group" yaml:"vlan_group"`
	Vlan          string   `json:"vlan" yaml:"vlan"`
	TenantGroup   string   `json:"tenant_group" yaml:"tenant_group"`
	Tenant        string   `json:"tenant" yaml:"tenant"`
	Tags          []string `json:"tags" yaml:"tags"`
}
