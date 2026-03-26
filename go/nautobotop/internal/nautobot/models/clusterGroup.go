package models

type ClusterGroups struct {
	ClusterGroup []ClusterGroup
}

type ClusterGroup struct {
	Name        string `json:"name" yaml:"name"`
	Description string `json:"description" yaml:"description"`
}
