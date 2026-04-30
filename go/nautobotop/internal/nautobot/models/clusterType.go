package models

type ClusterTypes struct {
	ClusterType []ClusterType
}

type ClusterType struct {
	ID          string `json:"id" yaml:"id"`
	Name        string `json:"name" yaml:"name"`
	Description string `json:"description" yaml:"description"`
}
