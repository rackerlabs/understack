package models

type Namespaces struct {
	Namespace []Namespace
}

type Namespace struct {
	ID          string `json:"id" yaml:"id"`
	Name        string `json:"name" yaml:"name"`
	Description string `json:"description" yaml:"description"`
	Location    string `json:"location" yaml:"location"`
	TenantGroup string `json:"tenant_group" yaml:"tenant_group"`
	Tenant      string `json:"tenant" yaml:"tenant"`
}
