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

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	git "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
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

	repoPath := fmt.Sprintf("gitcache/%s", watcher.Name)

	repo, err := git.PlainOpen(repoPath)
	switch err {
	case git.ErrRepositoryNotExists: // If repo Not Exist, Clone It
		log.Info("Cloning new repository", "url", watcher.Spec.RepoURL)
		err := GitClone(repoPath, watcher.Spec.RepoURL, watcher.Spec.Ref)
		if err != nil {
			log.Error(err, "Failed to clone Git repository")

			return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, nil
		}
		repo, _ = git.PlainOpen(repoPath) // Try again after clone
	case nil: // If repo already exists, pull it.
		log.Info("Pulling latest changes", "path", repoPath)
		err := GitPull(repo, watcher.Spec.Ref)
		if err != nil && err != git.NoErrAlreadyUpToDate {
			log.Error(err, "Git pull failed")

			return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, nil
		}
	default:
		log.Error(err, "Failed to open Git repository")
		return ctrl.Result{}, err
	}

	// Get latest commit SHA
	head, err := repo.Head()
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, nil
	}

	sha := head.Hash().String()
	log.Info("Repository sync complete", "commit", sha)

	// Update status
	watcher.Status.LatestCommitSHA = sha
	watcher.Status.SyncedAt = metav1.Now()
	watcher.Status.Ready = true
	watcher.Status.RepoPath = repoPath
	watcher.Status.Message = "Sync successful"
	if err := r.Status().Update(ctx, &watcher); err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(watcher.Spec.SyncIntervalSeconds) * time.Second}, nil
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

func GitClone(repoPath, url, ref string) error {
	_, err := git.PlainClone(repoPath, false, &git.CloneOptions{
		URL:           url,
		ReferenceName: plumbing.NewBranchReferenceName(ref),
		SingleBranch:  true,
		Depth:         1,
	})
	return err
}

func GitPull(repo *git.Repository, ref string) error {
	w, err := repo.Worktree()
	if err != nil {
		return err
	}
	return w.Pull(&git.PullOptions{
		RemoteName:    "origin",
		Depth:         1,
		ReferenceName: plumbing.NewBranchReferenceName(ref),
		Force:         true,
	})
}
