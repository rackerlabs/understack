package models

type RackGroups struct {
	RackGroup []RackGroup
}

type RackGroup struct {
	ID          string      `json:"id" yaml:"id"`
	Name        string      `json:"name" yaml:"name"`
	Description string      `json:"description" yaml:"description"`
	Location    string      `json:"location" yaml:"location"`
	Children    []RackGroup `json:"children" yaml:"children"`
}
