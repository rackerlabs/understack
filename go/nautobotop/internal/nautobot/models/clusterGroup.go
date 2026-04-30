package models

type ClusterGroups struct {
	ClusterGroup []ClusterGroup
}

type ClusterGroup struct {
	ID          string `json:"id" yaml:"id"`
	Name        string `json:"name" yaml:"name"`
	Description string `json:"description" yaml:"description"`
}
