package models

type VlanGroups struct {
	VlanGroup []VlanGroup
}

type VlanGroup struct {
	Name       string `json:"name" yaml:"name"`
	Location   string `json:"location" yaml:"location"`
	UcvniGroup string `json:"ucvni_group" yaml:"ucvni_group"`
	Range      string `json:"range" yaml:"range"`
}
