package models

type VlanGroups struct {
	VlanGroup []VlanGroup
}

type VlanGroup struct {
	Name           string `json:"name" yaml:"name"`
	Location       string `json:"location" yaml:"location"`
	UcvniGroupName string `json:"ucvni_group_name" yaml:"ucvni_group_name"`
	Range          string `json:"range" yaml:"range"`
}
