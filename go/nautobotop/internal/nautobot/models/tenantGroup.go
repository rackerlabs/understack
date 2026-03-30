package models

type TenantGroups struct {
	TenantGroup []TenantGroup
}

type TenantGroup struct {
	Name        string `json:"name" yaml:"name"`
	Description string `json:"description" yaml:"description"`
	Parent      string `json:"parent" yaml:"parent"`
}
