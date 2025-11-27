package v1alpha1

// ConfigMapRef defines a reference to a specific ConfigMap
type ConfigMapRef struct {
	// Name of this config set (logical name)
	Name string `json:"name"`

	// The name of the ConfigMap resource being referred to
	ConfigMapSelector ConfigMapKeySelector `json:"configMapSelector"`
}

// ConfigMapKeySelector selects a specific key from a ConfigMap in a namespace
type ConfigMapKeySelector struct {
	// The name of the ConfigMap
	// +kubebuilder:validation:MinLength=1
	Name string `json:"name"`

	// The namespace where the ConfigMap resides
	// +optional
	Namespace *string `json:"namespace,omitempty"`

	// The key in the ConfigMap data
	// +optional
	Key string `json:"key,omitempty"`
}
