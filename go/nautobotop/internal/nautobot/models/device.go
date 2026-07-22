package models

type Devices struct {
	Devices []Device
}

type Device struct {
	ID                string `json:"id" yaml:"id"`
	Name              string `json:"name" yaml:"name"`
	DeviceType        string `json:"device_type" yaml:"device_type"`
	Role              string `json:"role" yaml:"role"`
	Serial            string `json:"serial" yaml:"serial"`
	AssetTag          string `json:"asset_tag" yaml:"asset_tag"`
	Status            string `json:"status" yaml:"status"`
	Location          string `json:"location" yaml:"location"`
	Rack              string `json:"rack" yaml:"rack"`
	Position          int    `json:"position" yaml:"position"`
	Face              string `json:"face" yaml:"face"`
	Tenant            string `json:"tenant" yaml:"tenant"`
	Platform          string `json:"platform" yaml:"platform"`
	Comments          string `json:"comments" yaml:"comments"`
	ChassisMacAddress string `json:"chassis_mac_address" yaml:"chassis_mac_address"`
	ExternalCmdbID    string `json:"external_cmdb_id" yaml:"external_cmdb_id"`
	VlanGroup         string `json:"vlan_group" yaml:"vlan_group"`
}
