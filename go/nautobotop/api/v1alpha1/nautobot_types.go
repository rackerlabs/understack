/*
Copyright 2025.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// EDIT THIS FILE!  THIS IS SCAFFOLDING FOR YOU TO OWN!
// NOTE: json tags are required.  Any new fields you add must have json tags for the fields to be serialized.

// NautobotSpec defines the desired state of Nautobot.
type NautobotSpec struct {
	// +kubebuilder:default=600
	RequeueAfter int `json:"requeueAfter,omitempty"`
	// +kubebuilder:default=172800
	SyncIntervalSeconds int               `json:"syncIntervalSeconds,omitempty"`
	NautobotSecretRef   SecretKeySelector `json:"nautobotSecretRef,omitempty"`
	NautobotServiceRef  ServiceSelector   `json:"nautobotServiceRef,omitempty"`
	DeviceTypesRef      []ConfigMapRef    `json:"deviceTypeRef,omitempty"`
	LocationTypesRef    []ConfigMapRef    `json:"locationTypesRef,omitempty"`
}

// NautobotStatus defines the observed state of Nautobot.
type NautobotStatus struct {
	LastSyncedAt         metav1.Time         `json:"lastSyncedAt,omitempty"`
	Ready                bool                `json:"ready,omitempty"`
	Message              string              `json:"message,omitempty"`
	SyncHash             map[string]string   `json:"syncHash,omitempty"`
	NautobotStatusReport map[string][]string `json:"nautobotStatusReport,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:scope=Cluster

// Nautobot is the Schema for the nautobots API.
type Nautobot struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   NautobotSpec   `json:"spec,omitempty"`
	Status NautobotStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// NautobotList contains a list of Nautobot.
type NautobotList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []Nautobot `json:"items"`
}

func init() {
	SchemeBuilder.Register(&Nautobot{}, &NautobotList{})
}

func (r *Nautobot) GetSyncHash(key string) string {
	if r == nil || r.Status.SyncHash == nil {
		return ""
	}
	return r.Status.SyncHash[key]
}

func (r *Nautobot) SetSyncHash(key, value string) {
	if r.Status.SyncHash == nil {
		r.Status.SyncHash = make(map[string]string)
	}
	if value == "" {
		delete(r.Status.SyncHash, key)
	} else {
		r.Status.SyncHash[key] = value
	}
}
