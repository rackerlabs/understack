package models

type Locations struct {
	Location []Location
}

type Location struct {
	Name         string     `json:"name" yaml:"name"`
	Description  string     `json:"description" yaml:"description"`
	LocationType string     `json:"string" yaml:"location_type"`
	Status       string     `json:"status" yaml:"status"`
	Children     []Location `json:"children" yaml:"children"`
}
