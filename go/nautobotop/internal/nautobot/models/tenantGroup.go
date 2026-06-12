package models

type TenantGroups struct {
	TenantGroup []TenantGroup
}

type TenantGroup struct {
	ID          string `json:"id" yaml:"id"`
	Name        string `json:"name" yaml:"name"`
	Description string `json:"description" yaml:"description"`
	Parent      string `json:"parent" yaml:"parent"`
}
