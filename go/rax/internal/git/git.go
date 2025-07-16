package git

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/object"
	githttp "github.com/go-git/go-git/v5/plumbing/transport/http"
)

type Git struct {
	clonePath string
	remoteURL string
	ref       string
	username  string
	password  string
}

func NewGit(clonePath, remoteURL, ref, username, password string) *Git {
	return &Git{
		clonePath: clonePath,
		remoteURL: remoteURL,
		ref:       ref,
		username:  username,
		password:  password,
	}
}

// Sync clones if missing or dirty, then pulls latest changes.
func (g *Git) Sync() (*git.Repository, error) {
	repo, err := git.PlainOpen(g.clonePath)
	if err == git.ErrRepositoryNotExists {
		if err := g.Clone(); err != nil {
			return nil, fmt.Errorf("failed to clone repo: %w", err)
		}
		return git.PlainOpen(g.clonePath)
	} else if err != nil {
		return nil, fmt.Errorf("failed to open repo: %w", err)
	}

	dirty, err := g.IsDirty()
	if err != nil {
		return nil, fmt.Errorf("failed to check if repo is dirty: %w", err)
	}
	if dirty {
		// Remove the existing clone
		if err := os.RemoveAll(g.clonePath); err != nil {
			return nil, fmt.Errorf("failed to delete dirty repo: %w", err)
		}
		// Reclone fresh
		if err := g.Clone(); err != nil {
			return nil, fmt.Errorf("failed to re-clone dirty repo: %w", err)
		}
		return git.PlainOpen(g.clonePath)
	}

	if err := g.Pull(); err != nil && err != git.NoErrAlreadyUpToDate {
		return nil, fmt.Errorf("failed to pull repo: %w", err)
	}

	return repo, nil
}

// Clone performs a shallow clone of the specified branch.
func (g *Git) Clone() error {
	_, err := git.PlainClone(g.clonePath, false, &git.CloneOptions{
		URL:           g.remoteURL,
		ReferenceName: plumbing.NewBranchReferenceName(g.ref),
		SingleBranch:  true,
		Depth:         1,
		Auth: &githttp.BasicAuth{
			Username: g.username,
			Password: g.password,
		},
	})
	return err
}

// Pull updates the local repo by pulling changes from remote.
func (g *Git) Pull() error {
	repo, err := git.PlainOpen(g.clonePath)
	if err != nil {
		return fmt.Errorf("open repo for pull: %w", err)
	}

	worktree, err := repo.Worktree()
	if err != nil {
		return fmt.Errorf("get worktree: %w", err)
	}

	return worktree.Pull(&git.PullOptions{
		RemoteName:    "origin",
		ReferenceName: plumbing.NewBranchReferenceName(g.ref),
		SingleBranch:  true,
		Depth:         1,
		Force:         true,
		Auth: &githttp.BasicAuth{
			Username: g.username,
			Password: g.password,
		},
	})
}

// GetLastFileCommitSHA returns the last commit SHA that modified a file.
func (g *Git) GetLastFileCommitSHA(filePath string) (string, error) {
	repo, err := git.PlainOpen(g.clonePath)
	if err != nil {
		return "", fmt.Errorf("open repo: %w", err)
	}

	ref, err := repo.Head()
	if err != nil {
		return "", fmt.Errorf("get HEAD: %w", err)
	}

	logIter, err := repo.Log(&git.LogOptions{From: ref.Hash()})
	if err != nil {
		return "", fmt.Errorf("get commit log: %w", err)
	}
	defer logIter.Close() //nolint:errcheck

	normalizedPath := filepath.ToSlash(filePath)

	for {
		commit, err := logIter.Next()
		if err != nil {
			break
		}

		files, err := commit.Files()
		if err != nil {
			return "", fmt.Errorf("get commit files: %w", err)
		}

		var found bool
		_ = files.ForEach(func(f *object.File) error {
			if f.Name == normalizedPath {
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

// IsDirty returns true if the working directory has uncommitted changes.
func (g *Git) IsDirty() (bool, error) {
	repo, err := git.PlainOpen(g.clonePath)
	if err != nil {
		return false, fmt.Errorf("open repo: %w", err)
	}

	worktree, err := repo.Worktree()
	if err != nil {
		return false, fmt.Errorf("get worktree: %w", err)
	}

	status, err := worktree.Status()
	if err != nil {
		return false, fmt.Errorf("get status: %w", err)
	}

	return !status.IsClean(), nil
}
