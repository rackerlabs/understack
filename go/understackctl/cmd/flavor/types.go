package flavor

// Flavor represents a hardware flavor definition
type Flavor struct {
	Name          string  `yaml:"name" json:"name"`
	ResourceClass string  `yaml:"resource_class" json:"resource_class"`
	Traits        []Trait `yaml:"traits,omitempty" json:"traits,omitempty"`
}

// Trait represents a hardware trait requirement
type Trait struct {
	Trait       string `yaml:"trait" json:"trait"`
	Requirement string `yaml:"requirement" json:"requirement"`
}
