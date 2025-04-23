/*
Copyright 2025 Rackspace Technology.

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
	"fmt"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	dexv1alpha1 "github.com/rackerlabs/understack/go/dexop/api/v1alpha1"
	dexmgr "github.com/rackerlabs/understack/go/dexop/dex"
)

func newDexMgr() (*dexmgr.DexManager, error) {
	mgr, err := dexmgr.NewDexManager("127.0.0.1:5557", "/home/skrobul/devel/understack/go/dexop/grpc_ca.crt", "/home/skrobul/devel/understack/go/dexop/grpc_client.key", "/home/skrobul/devel/understack/go/dexop/grpc_client.crt")
	if err != nil {
		return nil, fmt.Errorf("While getting the DexManager")
	}
	return mgr, err
}

var _ = Describe("Client Controller", func() {
	const resourceName = "test-resource"
	const secretName = "freds-secret"
	ctx := context.Background()

	Context("When reconciling a resource", func() {
		typeNamespacedName := types.NamespacedName{
			Name:      resourceName,
			Namespace: "default",
		}
		typesNamespacedSecretName := types.NamespacedName{Namespace: typeNamespacedName.Namespace, Name: secretName}
		client := &dexv1alpha1.Client{}
		dex, err := newDexMgr()
		Expect(err).NotTo(HaveOccurred())

		BeforeEach(func() {
			By("creating the custom resource for the Kind Client")
			err := k8sClient.Get(ctx, typeNamespacedName, client)
			if err != nil && errors.IsNotFound(err) {
				resource := &dexv1alpha1.Client{
					ObjectMeta: metav1.ObjectMeta{
						Name:      resourceName,
						Namespace: "default",
					},
					Spec: dexv1alpha1.ClientSpec{
						Name:           "fred-client",
						SecretName:     secretName,
						GenerateSecret: true,
						RedirectURIs:   []string{"http://localhost:8080", "https://some.service.example.com/callback"},
						LogoUrl:        "http://logoserver.local/xyz.png",
					},
				}
				Expect(k8sClient.Create(ctx, resource)).To(Succeed())
			}
		})

		AfterEach(func() {
			resource := &dexv1alpha1.Client{}
			By("lookup of the existing resource")
			err := k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(err).NotTo(HaveOccurred())

			By("Cleanup the specific resource instance Client")
			Expect(k8sClient.Delete(ctx, resource)).To(Succeed())
			// we need to run reconciler again to process finalizer
			controllerReconciler := &ClientReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
			}
			_, err = controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})

			Expect(err).NotTo(HaveOccurred())
			Eventually(func() bool {
				err := k8sClient.Get(ctx, typeNamespacedName, &dexv1alpha1.Client{})
				return errors.IsNotFound(err)
			}, 15*time.Second, 500*time.Millisecond).Should(BeTrue())
		})

		It("should create a secret with a non-empty value", func() {
			controllerReconciler := &ClientReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
			}

			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			secretObj := &v1.Secret{}
			k8sClient.Get(ctx, types.NamespacedName{Namespace: typeNamespacedName.Namespace, Name: secretName}, secretObj)
			Expect(len(secretObj.Data["secret"])).To(Equal(48))
			Expect(err).NotTo(HaveOccurred())
		})
		It("should successfully reconcile the resource", func() {
			By("Reconciling the created resource")
			controllerReconciler := &ClientReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
			}

			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())
		})
		It("should update the password after secret changes", func() {
			By("Reconciling the created resource")
			controllerReconciler := &ClientReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
			}

			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())
			secretObj := &v1.Secret{}
			Expect(k8sClient.Get(ctx, typesNamespacedSecretName, secretObj)).To(Succeed())
			secretObj.Data["secret"] = []byte("newSecret")

			By("reconcile after changing the secret")
			Expect(k8sClient.Update(ctx, secretObj)).To(Succeed())
			_, err = controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("verifying if the Dex side was updated")
			dexclient, err := dex.GetOauth2Client("fred-client")
			Expect(err).NotTo(HaveOccurred())
			Expect(dexclient.Client.Secret).To(Equal("newSecret"))
		})
		It("updates RedirectURIs", func() {
			By("updating redirectURIs in dex")
			controllerReconciler := &ClientReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
			}
			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			resource := &dexv1alpha1.Client{}
			Expect(k8sClient.Get(ctx, typeNamespacedName, resource)).To(Succeed())
			resource.Spec.RedirectURIs = []string{"https://new.redirect.local"}
			Expect(k8sClient.Update(ctx, resource)).To(Succeed())

			By("reconciling again")
			_, err = controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("checking if the RedirectURIs have been updated in Dex")
			dexclient, err := dex.GetOauth2Client("fred-client")
			Expect(err).NotTo(HaveOccurred())
			Expect(dexclient.Client.RedirectUris).To(Equal([]string{"https://new.redirect.local"}))
		})

		It("creates the secret if it is missing", func() {
			By("reconciling the first time")
			controllerReconciler := &ClientReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
			}
			_, err := controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("deleting the Secret")
			secret := &v1.Secret{ObjectMeta: metav1.ObjectMeta{Name: typesNamespacedSecretName.Name, Namespace: typesNamespacedSecretName.Namespace}}
			Expect(k8sClient.Delete(ctx, secret)).To(Succeed())
			Expect(k8sClient.Get(ctx, typesNamespacedSecretName, secret)).NotTo(Succeed())

			By("doing another round of reconciliation")
			_, err = controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			By("checking if the Secret has been recreated")
			newSecret := &v1.Secret{ObjectMeta: metav1.ObjectMeta{Name: typesNamespacedSecretName.Name, Namespace: typesNamespacedSecretName.Namespace}}
			Expect(k8sClient.Get(ctx, typesNamespacedSecretName, newSecret))
		})
	})

	Context("pre-created Secret", func() {
		typeNamespacedName := types.NamespacedName{
			Name:      resourceName,
			Namespace: "default",
		}
		dex, err := newDexMgr()
		Expect(err).NotTo(HaveOccurred())
		It("copies the secret value", func() {
			By("creating Client resource")
			testSecretName := "test-secret-123"
			resource := &dexv1alpha1.Client{
				ObjectMeta: metav1.ObjectMeta{
					Name:      resourceName,
					Namespace: "default",
				},
				Spec: dexv1alpha1.ClientSpec{
					Name:           "fred-client",
					SecretName:     testSecretName,
					GenerateSecret: false,
					RedirectURIs:   []string{"http://localhost:8080", "https://some.service.example.com/callback"},
				},
			}
			Expect(k8sClient.Create(ctx, resource)).To(Succeed())

			By("creating secret")
			secret := &v1.Secret{
				ObjectMeta: metav1.ObjectMeta{Name: testSecretName, Namespace: "default"},
				Data:       map[string][]byte{"secret": []byte("abc")},
			}
			Expect(k8sClient.Create(ctx, secret)).To(Succeed())

			By("doing another round of reconciliation")
			controllerReconciler := &ClientReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
			}
			_, err = controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})
			Expect(err).NotTo(HaveOccurred())

			dexclient, err := dex.GetOauth2Client("fred-client")
			Expect(err).NotTo(HaveOccurred())
			Expect(dexclient.Client.Secret).To(Equal("abc"))
		})

		AfterEach(func() {
			resource := &dexv1alpha1.Client{}
			By("lookup of the existing resource")
			err := k8sClient.Get(ctx, typeNamespacedName, resource)
			Expect(err).NotTo(HaveOccurred())

			By("Cleanup the specific resource instance Client")
			Expect(k8sClient.Delete(ctx, resource)).To(Succeed())
			// we need to run reconciler again to process finalizer
			controllerReconciler := &ClientReconciler{
				Client: k8sClient,
				Scheme: k8sClient.Scheme(),
			}
			_, err = controllerReconciler.Reconcile(ctx, reconcile.Request{
				NamespacedName: typeNamespacedName,
			})

			Expect(err).NotTo(HaveOccurred())
			Eventually(func() bool {
				err := k8sClient.Get(ctx, typeNamespacedName, &dexv1alpha1.Client{})
				return errors.IsNotFound(err)
			}, 15*time.Second, 500*time.Millisecond).Should(BeTrue())
		})
	})
})
