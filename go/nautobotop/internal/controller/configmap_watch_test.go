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

package controller

import (
	"context"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/ptr"

	syncv1alpha1 "github.com/rackerlabs/understack/go/nautobotop/api/v1alpha1"
)

var _ = Describe("ConfigMap Watch", func() {

	Context("referencesConfigMap", func() {
		var reconciler *NautobotReconciler

		BeforeEach(func() {
			reconciler = &NautobotReconciler{}
		})

		It("returns true when the Nautobot CR references the ConfigMap by name and namespace", func() {
			nb := &syncv1alpha1.Nautobot{
				Spec: syncv1alpha1.NautobotSpec{
					DeviceTypesRef: []syncv1alpha1.ConfigMapRef{
						{ConfigMapSelector: syncv1alpha1.ConfigMapKeySelector{
							Name:      "device-types-cm",
							Namespace: ptr.To("infra"),
						}},
					},
				},
			}
			Expect(reconciler.referencesConfigMap(nb, "device-types-cm", "infra")).To(BeTrue())
		})

		It("returns false when namespace does not match", func() {
			nb := &syncv1alpha1.Nautobot{
				Spec: syncv1alpha1.NautobotSpec{
					DeviceTypesRef: []syncv1alpha1.ConfigMapRef{
						{ConfigMapSelector: syncv1alpha1.ConfigMapKeySelector{
							Name:      "device-types-cm",
							Namespace: ptr.To("infra"),
						}},
					},
				},
			}
			Expect(reconciler.referencesConfigMap(nb, "device-types-cm", "other-ns")).To(BeFalse())
		})

		It("returns false when name does not match", func() {
			nb := &syncv1alpha1.Nautobot{
				Spec: syncv1alpha1.NautobotSpec{
					LocationRef: []syncv1alpha1.ConfigMapRef{
						{ConfigMapSelector: syncv1alpha1.ConfigMapKeySelector{
							Name:      "locations-cm",
							Namespace: ptr.To("infra"),
						}},
					},
				},
			}
			Expect(reconciler.referencesConfigMap(nb, "other-cm", "infra")).To(BeFalse())
		})

		It("returns false when the CR has no ConfigMap references", func() {
			nb := &syncv1alpha1.Nautobot{
				Spec: syncv1alpha1.NautobotSpec{},
			}
			Expect(reconciler.referencesConfigMap(nb, "any-cm", "any-ns")).To(BeFalse())
		})

		It("handles nil namespace in the ref (matches empty namespace)", func() {
			nb := &syncv1alpha1.Nautobot{
				Spec: syncv1alpha1.NautobotSpec{
					RackRef: []syncv1alpha1.ConfigMapRef{
						{ConfigMapSelector: syncv1alpha1.ConfigMapKeySelector{
							Name:      "rack-cm",
							Namespace: nil,
						}},
					},
				},
			}
			// nil namespace in ref means empty string — matches a ConfigMap with empty namespace
			Expect(reconciler.referencesConfigMap(nb, "rack-cm", "")).To(BeTrue())
			Expect(reconciler.referencesConfigMap(nb, "rack-cm", "some-ns")).To(BeFalse())
		})

		It("matches across multiple ref fields", func() {
			nb := &syncv1alpha1.Nautobot{
				Spec: syncv1alpha1.NautobotSpec{
					VlanRef: []syncv1alpha1.ConfigMapRef{
						{ConfigMapSelector: syncv1alpha1.ConfigMapKeySelector{
							Name:      "vlan-cm",
							Namespace: ptr.To("network"),
						}},
					},
					PrefixRef: []syncv1alpha1.ConfigMapRef{
						{ConfigMapSelector: syncv1alpha1.ConfigMapKeySelector{
							Name:      "prefix-cm",
							Namespace: ptr.To("network"),
						}},
					},
				},
			}
			Expect(reconciler.referencesConfigMap(nb, "prefix-cm", "network")).To(BeTrue())
			Expect(reconciler.referencesConfigMap(nb, "vlan-cm", "network")).To(BeTrue())
			Expect(reconciler.referencesConfigMap(nb, "unknown-cm", "network")).To(BeFalse())
		})
	})

	Context("configMapToNautobotRequests", func() {
		var reconciler *NautobotReconciler

		BeforeEach(func() {
			reconciler = &NautobotReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
			}
		})

		It("returns reconcile requests for CRs that reference the changed ConfigMap", func() {
			ctx := context.Background()

			// Create a Nautobot CR that references a specific ConfigMap
			nb := &syncv1alpha1.Nautobot{
				ObjectMeta: metav1.ObjectMeta{
					Name: "watch-test-cr",
				},
				Spec: syncv1alpha1.NautobotSpec{
					LocationRef: []syncv1alpha1.ConfigMapRef{
						{ConfigMapSelector: syncv1alpha1.ConfigMapKeySelector{
							Name:      "locations-data",
							Namespace: ptr.To("test-ns"),
						}},
					},
				},
			}
			Expect(k8sClient.Create(ctx, nb)).To(Succeed())
			defer func() {
				_ = k8sClient.Delete(ctx, nb)
			}()

			// Simulate a ConfigMap change event
			changedCM := &corev1.ConfigMap{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "locations-data",
					Namespace: "test-ns",
				},
			}

			requests := reconciler.configMapToNautobotRequests(ctx, changedCM)
			Expect(requests).To(HaveLen(1))
			Expect(requests[0].NamespacedName).To(Equal(types.NamespacedName{Name: "watch-test-cr"}))
		})

		It("returns empty when no CR references the changed ConfigMap", func() {
			ctx := context.Background()

			nb := &syncv1alpha1.Nautobot{
				ObjectMeta: metav1.ObjectMeta{
					Name: "watch-test-cr-no-match",
				},
				Spec: syncv1alpha1.NautobotSpec{
					RackRef: []syncv1alpha1.ConfigMapRef{
						{ConfigMapSelector: syncv1alpha1.ConfigMapKeySelector{
							Name:      "racks-data",
							Namespace: ptr.To("infra"),
						}},
					},
				},
			}
			Expect(k8sClient.Create(ctx, nb)).To(Succeed())
			defer func() {
				_ = k8sClient.Delete(ctx, nb)
			}()

			// ConfigMap that nobody references
			changedCM := &corev1.ConfigMap{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "unrelated-cm",
					Namespace: "infra",
				},
			}

			requests := reconciler.configMapToNautobotRequests(ctx, changedCM)
			Expect(requests).To(BeEmpty())
		})
	})
})
