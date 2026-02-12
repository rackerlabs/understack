package models

type Racks struct {
	Rack []Rack
}

type Rack struct {
	Name        string `json:"name" yaml:"name"`
	Facility    string `json:"facility" yaml:"facility"`
	Description string `json:"description" yaml:"description"`
	Location    string `json:"location" yaml:"location"`
	RackGroup   string `json:"rack_group" yaml:"rack_group"`
	Status      string `json:"status" yaml:"status"`
	UHeight     int    `json:"u_height" yaml:"u_height"`
}
