package models

type ClusterTypes struct {
	ClusterType []ClusterType
}

type ClusterType struct {
	Name        string `json:"name" yaml:"name"`
	Description string `json:"description" yaml:"description"`
}
