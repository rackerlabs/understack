package models

type Tenants struct {
	Tenant []Tenant
}

type Tenant struct {
	Name        string   `json:"name" yaml:"name"`
	Description string   `json:"description" yaml:"description"`
	Comments    string   `json:"comments" yaml:"comments"`
	TenantGroup string   `json:"tenant_group" yaml:"tenant_group"`
	Tags        []string `json:"tags" yaml:"tags"`
}
