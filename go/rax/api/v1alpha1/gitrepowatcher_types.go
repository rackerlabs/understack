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

// GitRepoWatcherSpec defines the desired state of GitRepoWatcher.
type GitRepoWatcherSpec struct {
	RepoURL    string `json:"repoURL"`
	GitOrgName string `json:"gitOrgName"`
	Ref        string `json:"ref"` // branch or tag
	// +kubebuilder:default=60
	SyncIntervalSeconds int      `json:"syncIntervalSeconds,omitempty"`
	Secrets             []Secret `json:"secrets,omitempty"`
}

// GitRepoWatcherStatus defines the observed state of GitRepoWatcher.
type GitRepoWatcherStatus struct {
	GitCommitHash string      `json:"gitCommitHash,omitempty"`
	RepoClonePath string      `json:"repoClonePath,omitempty"`
	LastSyncedAt  metav1.Time `json:"lastSyncedAt,omitempty"`
	Ready         bool        `json:"ready,omitempty"`
	Message       string      `json:"message,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:resource:scope=Cluster
// +kubebuilder:subresource:status

// GitRepoWatcher is the Schema for the gitrepowatchers API.
type GitRepoWatcher struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   GitRepoWatcherSpec   `json:"spec,omitempty"`
	Status GitRepoWatcherStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// GitRepoWatcherList contains a list of GitRepoWatcher.
type GitRepoWatcherList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []GitRepoWatcher `json:"items"`
}

func init() {
	SchemeBuilder.Register(&GitRepoWatcher{}, &GitRepoWatcherList{})
}
