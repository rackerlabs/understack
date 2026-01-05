package models

type DeviceTypes struct {
	DeviceTypes []DeviceType
}

type DeviceType struct {
	Manufacturer  string          `yaml:"manufacturer"`
	PartNumber    string          `yaml:"part_number"`
	Model         string          `yaml:"model"`
	UHeight       int             `yaml:"u_height"`
	IsFullDepth   bool            `yaml:"is_full_depth"`
	Comments      string          `yaml:"comments"`
	ConsolePorts  []ConsolePort   `yaml:"console-ports"`
	PowerPorts    []PowerPort     `yaml:"power-ports"`
	Interfaces    []Interface     `yaml:"interfaces"`
	ModuleBays    []ModuleBay     `yaml:"module-bays"`
	Class         string          `yaml:"class"`
	ResourceClass []ResourceClass `yaml:"resource_class"`
}

type ResourceClass struct {
	Name     string `yaml:"name"`
	CPU      CPU    `yaml:"cpu"`
	Memory   Memory `yaml:"memory"`
	Drives   []Disk `yaml:"drives"`
	NicCount int    `yaml:"nic_count"`
}

type CPU struct {
	Cores int    `yaml:"cores"`
	Model string `yaml:"model"`
}

type Memory struct {
	Size int `yaml:"size"`
}

type Disk struct {
	Size int `yaml:"size"`
}

type ConsolePort struct {
	Name string `yaml:"name"`
	Type string `yaml:"type"`
}

type PowerPort struct {
	Name          string `yaml:"name"`
	Type          string `yaml:"type"`
	MaximumDraw   int    `yaml:"maximum_draw"`
	AllocatedDraw int    `yaml:"allocated_draw"`
}

type Interface struct {
	Name     string `yaml:"name"`
	Type     string `yaml:"type"`
	MgmtOnly bool   `yaml:"mgmt_only"`
}

type ModuleBay struct {
	Name     string `yaml:"name"`
	Position string `yaml:"position"`
	Label    string `yaml:"label,omitempty"`
}
