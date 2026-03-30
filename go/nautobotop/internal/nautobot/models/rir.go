package models

type Rirs struct {
	Rir []Rir
}

type Rir struct {
	Name        string `json:"name" yaml:"name"`
	IsPrivate   bool   `json:"is_private" yaml:"is_private"`
	Description string `json:"description" yaml:"description"`
}
