package models

type LocationTypes struct {
	LocationType []LocationType
}

type LocationType struct {
	Name         string         `json:"name" yaml:"name"`
	Description  string         `json:"description" yaml:"description"`
	ContentTypes []string       `json:"content_types" yaml:"content_types"`
	Nestable     bool           `json:"nestable" yaml:"nestable"`
	Children     []LocationType `json:"children" yaml:"children"`
}
