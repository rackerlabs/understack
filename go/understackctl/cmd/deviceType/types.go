package deviceType

// DeviceType represents a hardware device type definition
type DeviceType struct {
	Class         string          `yaml:"class" json:"class"`
	Manufacturer  string          `yaml:"manufacturer" json:"manufacturer"`
	Model         string          `yaml:"model" json:"model"`
	UHeight       float64         `yaml:"u_height" json:"u_height"`
	IsFullDepth   bool            `yaml:"is_full_depth" json:"is_full_depth"`
	Interfaces    []Interface     `yaml:"interfaces,omitempty" json:"interfaces,omitempty"`
	ResourceClass []ResourceClass `yaml:"resource_class,omitempty" json:"resource_class,omitempty"`
}

// Interface represents a network interface
type Interface struct {
	Name       string `yaml:"name" json:"name"`
	Type       string `yaml:"type" json:"type"`
	MgmtOnly   bool   `yaml:"mgmt_only,omitempty" json:"mgmt_only,omitempty"`
	DetectOnly bool   `yaml:"detect_only,omitempty" json:"detect_only,omitempty"`
}

// ResourceClass represents a hardware configuration profile
type ResourceClass struct {
	Name     string  `yaml:"name" json:"name"`
	CPU      CPU     `yaml:"cpu" json:"cpu"`
	Memory   Memory  `yaml:"memory" json:"memory"`
	Drives   []Drive `yaml:"drives" json:"drives"`
	NICCount int     `yaml:"nic_count" json:"nic_count"`
}

// CPU represents CPU specifications
type CPU struct {
	Cores int    `yaml:"cores" json:"cores"`
	Model string `yaml:"model" json:"model"`
}

// Memory represents memory specifications
type Memory struct {
	Size int `yaml:"size" json:"size"`
}

// Drive represents a storage drive
type Drive struct {
	Size int `yaml:"size" json:"size"`
}
