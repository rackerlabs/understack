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
	"os"
	"path/filepath"
	"time"

	"gopkg.in/yaml.v2"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"

	"sigs.k8s.io/controller-runtime/pkg/client"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	git "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing/object"
	syncv1alpha1 "github.com/rackerlabs/understack/go/sync/api/v1alpha1"
	"github.com/rackerlabs/understack/go/sync/internal/nautobot"
)

// NautobotReconciler reconciles a Nautobot object
type NautobotReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=sync.rax.io,resources=nautobots,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=sync.rax.io,resources=nautobots/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=sync.rax.io,resources=nautobots/finalizers,verbs=update

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
// TODO(user): Modify the Reconcile function to compare the state specified by
// the Nautobot object against the actual cluster state, and then
// perform operations to make the cluster state reflect the state specified by
// the user.
//
// For more details, check Reconcile and its Result here:
// - https://pkg.go.dev/sigs.k8s.io/controller-runtime@v0.20.4/pkg/reconcile
func (r *NautobotReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := logf.FromContext(ctx)

	var nautobotCR syncv1alpha1.Nautobot
	if err := r.Get(ctx, types.NamespacedName{Name: req.Name}, &nautobotCR); err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, client.IgnoreNotFound(err)
	}

	var gitRepoWatcher syncv1alpha1.GitRepoWatcher
	if err := r.Get(ctx, types.NamespacedName{Name: nautobotCR.Spec.RepoWatcher}, &gitRepoWatcher); err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, client.IgnoreNotFound(err)
	}

	var service corev1.Service
	if err := r.Get(ctx, types.NamespacedName{Namespace: "default", Name: "nautobot-default"}, &service); err != nil {
		log.Error(err, "failed to fetch Service nautobot-default")
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
	}

	if !gitRepoWatcher.Status.Ready {
		log.Info("git sync is not ready will retry")
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, nil
	}

	sha, _ := GetLastFileCommitSHA(gitRepoWatcher.Status.RepoPath, nautobotCR.Spec.ConfigPath)
	nautobotCR.Status.LatestCommitSHA = sha

	file, _ := os.ReadFile(fmt.Sprintf("%s/%s", gitRepoWatcher.Status.RepoPath, nautobotCR.Spec.ConfigPath))
	root, err := parseYAML(file)
	if err != nil {
		log.Error(err, "failed parse YAML")
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
	}
	for i := range root.InstanceLocations {
		setDisplayPath(&root.InstanceLocations[i], "")
	}
	var nautoBotAuthToken string
	for _, v := range nautobotCR.Spec.Env {
		if v.Name == "NAUTOBOT_TOKEN" {
			key := v.ValueFrom.SecretKeyRef.Key
			secretName := v.ValueFrom.SecretKeyRef.Name
			secret := &corev1.Secret{}
			err := r.Get(ctx, types.NamespacedName{Name: secretName, Namespace: "default"}, secret)
			if err != nil {
				if errors.IsNotFound(err) {
					log.Error(err, fmt.Sprintf("Secret %s not found in namespace %s for environment variable %s. Cannot retrieve secret value.", secretName, "", secretName))
					return ctrl.Result{}, fmt.Errorf("secret %s/%s not found: %w", "", secretName, err)
				}
				log.Error(err, fmt.Sprintf("Failed to get Secret %s/%s for environment variable %s", "", secretName, secretName))
				return ctrl.Result{}, err
			}

			// Read the secret value
			if valBytes, ok := secret.Data[key]; ok {
				nautoBotAuthToken = string(valBytes)
			} else {
				return ctrl.Result{}, fmt.Errorf("secret key %s not found in secret", key)
			}
		}
	}
	nb := nautobot.NewNautobotClient(fmt.Sprintf("http://%s/api", service.Spec.ClusterIP), nautoBotAuthToken)

	err = nb.SyncAllLocationTypes(ctx, root.LocationTypes)
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
	}

	err = nb.SyncAllLocations(ctx, root.InstanceLocations)
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
	}

	err = nb.SyncRackGroup(ctx, root.RackGroup)
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
	}

	err = nb.SyncRack(ctx, root.Rack)
	if err != nil {
		return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, err
	}

	return ctrl.Result{RequeueAfter: time.Duration(nautobotCR.Spec.SyncIntervalSeconds) * time.Second}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *NautobotReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&syncv1alpha1.Nautobot{}).
		Named("nautobot").
		Complete(r)
}

func parseYAML(data []byte) (*nautobot.NautobotYAML, error) {
	var cfg nautobot.NautobotYAML
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}

func setDisplayPath(loc *nautobot.Location, parentPath string) {
	if parentPath == "" {
		loc.Display = loc.Name
	} else {
		loc.Display = parentPath + " → " + loc.Name
	}
	for i := range loc.Children {
		setDisplayPath(&loc.Children[i], loc.Display)
	}
}

// IsGitRepoReady checks if the GitRepoWatcher has Ready condition set to True
func IsGitRepoReady(watcher *syncv1alpha1.GitRepoWatcher) bool {
	if watcher == nil {
		return false
	}

	return watcher.Status.Ready
}

// GetLastFileCommitSHA returns the last commit SHA that modified the given file.
func GetLastFileCommitSHA(repoPath, filePath string) (string, error) {
	repo, err := git.PlainOpen(repoPath)
	if err != nil {
		return "", err
	}

	ref, err := repo.Head()
	if err != nil {
		return "", err
	}

	logIter, err := repo.Log(&git.LogOptions{From: ref.Hash()})
	if err != nil {
		return "", err
	}

	relativePath := filepath.ToSlash(filePath) // Normalize path
	defer logIter.Close()

	for {
		commit, err := logIter.Next()
		if err != nil {
			break
		}

		files, err := commit.Files()
		if err != nil {
			return "", err
		}

		found := false
		_ = files.ForEach(func(f *object.File) error {
			if f.Name == relativePath {
				found = true
				return nil
			}
			return nil
		})

		if found {
			return commit.Hash.String(), nil
		}
	}

	return "", fmt.Errorf("no commit found for file: %s", filePath)
}
