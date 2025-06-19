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
	"fmt"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	"github.com/rackerlabs/understack/go/sync/internal/git"

	syncv1alpha1 "github.com/rackerlabs/understack/go/sync/api/v1alpha1"
)

// GitRepoWatcherReconciler reconciles a GitRepoWatcher object
type GitRepoWatcherReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=sync.rax.io,resources=gitrepowatchers,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=sync.rax.io,resources=gitrepowatchers/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=sync.rax.io,resources=gitrepowatchers/finalizers,verbs=update

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
// TODO(user): Modify the Reconcile function to compare the state specified by
// the GitRepoWatcher object against the actual cluster state, and then
// perform operations to make the cluster state reflect the state specified by
// the user.
//
// For more details, check Reconcile and its Result here:
// - https://pkg.go.dev/sigs.k8s.io/controller-runtime@v0.20.4/pkg/reconcile
func (r *GitRepoWatcherReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := logf.FromContext(ctx)
	log.Info("Reconciling", "name", req.Name)

	var watcher syncv1alpha1.GitRepoWatcher
	if err := r.Get(ctx, types.NamespacedName{Name: req.Name}, &watcher); err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, client.IgnoreNotFound(err)
	}

	repoClonePath := fmt.Sprintf("gitcache/%s", watcher.Name)

	appId, err := r.getAuthTokenFromSecretRef(ctx, watcher, "username")
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, err
	}
	privateKeyPEM, err := r.getAuthTokenFromSecretRef(ctx, watcher, "password")
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, err
	}
	githubToken, err := git.NewGithub(appId, watcher.Spec.GitOrgName, privateKeyPEM).GetToken(ctx)
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, err
	}
	git := git.NewGit(repoClonePath, watcher.Spec.RepoURL, watcher.Spec.Ref, appId, githubToken)
	repo, err := git.Sync()
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, err
	}
	// Get latest commit SHA
	head, err := repo.Head()
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, err
	}

	sha := head.Hash().String()
	log.Info("Repository sync complete", "commit", sha)

	// Update status
	watcher.Status.GitCommitHash = sha
	watcher.Status.LastSyncedAt = metav1.Now()
	watcher.Status.Ready = true
	watcher.Status.RepoClonePath = repoClonePath
	watcher.Status.Message = "Sync successful"
	if err := r.Status().Update(ctx, &watcher); err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, err
	}

	return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *GitRepoWatcherReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&syncv1alpha1.GitRepoWatcher{}).
		Named("gitrepowatcher").
		Complete(r)
}

func (r *GitRepoWatcherReconciler) getAuthTokenFromSecretRef(ctx context.Context, gitRepoWatcher syncv1alpha1.GitRepoWatcher, name string) (string, error) {
	for _, v := range gitRepoWatcher.Spec.Secrets {
		if v.Name == name {
			secret := &corev1.Secret{}
			err := r.Get(ctx, types.NamespacedName{Name: v.SecretRef.Name, Namespace: *v.SecretRef.Namespace}, secret)
			if err != nil {
				return "", err
			}
			// Read the secret value
			if valBytes, ok := secret.Data[v.SecretRef.Key]; ok {
				return string(valBytes), nil
			}
			return "", fmt.Errorf("secret key %s not found in secret", v.SecretRef.Key)
		}
	}
	return "", fmt.Errorf("failed to find %s", name)
}
