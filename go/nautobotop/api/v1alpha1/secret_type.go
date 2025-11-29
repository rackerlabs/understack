package v1alpha1

type SecretKeySelector struct {
	// The name of the Secret resource being referred to.
	// +kubebuilder:validation:MinLength:=1
	// +kubebuilder:validation:MaxLength:=253
	// +kubebuilder:validation:Pattern:=^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$
	Name string `json:"name,omitempty"`

	// The namespace of the Secret resource being referred to.
	// Ignored if referent is not cluster-scoped, otherwise defaults to the namespace of the referent.
	// +optional
	// +kubebuilder:validation:MinLength:=1
	// +kubebuilder:validation:MaxLength:=63
	// +kubebuilder:validation:Pattern:=^[a-z0-9]([-a-z0-9]*[a-z0-9])?$
	Namespace *string `json:"namespace,omitempty"`

	// A key in the referenced Secret.
	// Some instances of this field may be defaulted, in others it may be required.
	// +optional
	// +kubebuilder:validation:MinLength:=1
	// +kubebuilder:validation:MaxLength:=253
	// +kubebuilder:validation:Pattern:=^[-._a-zA-Z0-9]+$
	Key string `json:"key,omitempty"`
}
