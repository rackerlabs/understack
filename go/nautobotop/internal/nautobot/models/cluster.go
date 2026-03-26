package models

type Clusters struct {
	Cluster []Cluster
}

type Cluster struct {
	Name         string   `json:"name" yaml:"name"`
	Comments     string   `json:"comments" yaml:"comments"`
	ClusterType  string   `json:"cluster_type" yaml:"cluster_type"`
	ClusterGroup string   `json:"cluster_group" yaml:"cluster_group"`
	Location     string   `json:"location" yaml:"location"`
	Devices      []string `json:"devices" yaml:"devices"`
}
