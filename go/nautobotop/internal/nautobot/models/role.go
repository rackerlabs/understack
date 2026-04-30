package models

type Roles struct {
	Role []Role
}

type Role struct {
	ID           string   `json:"id" yaml:"id"`
	Name         string   `json:"name" yaml:"name"`
	Color        string   `json:"color" yaml:"color"`
	Description  string   `json:"description" yaml:"description"`
	Weight       int      `json:"weight" yaml:"weight"`
	ContentTypes []string `json:"content_types" yaml:"content_types"`
}
