package git

import (
	"fmt"
	"path/filepath"

	git "github.com/go-git/go-git/v5"
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

func (g *Git) Sync() (*git.Repository, error) {
	repo, err := git.PlainOpen(g.clonePath)
	switch err {
	case git.ErrRepositoryNotExists: // If repo Not Exist, Clone It
		err := g.GitClone()
		if err != nil {
			return nil, fmt.Errorf("failed to clone Git repository %s", err.Error())
		}
		repo, _ = git.PlainOpen(g.clonePath) // Try again after clone
	case nil: // If repo already exists, pull it.
		err := g.GitPull()
		if err != nil && err != git.NoErrAlreadyUpToDate {
			return nil, fmt.Errorf("failed to pull Git repository %s", err.Error())
		}
	default:
		return nil, err
	}
	return repo, err
}

func (g *Git) GitClone() error {
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

func (g *Git) GitPull() error {
	repo, err := git.PlainOpen(g.clonePath)
	if err != nil {
		return err
	}
	w, err := repo.Worktree()
	if err != nil {
		return err
	}
	return w.Pull(&git.PullOptions{
		RemoteName:    "origin",
		Depth:         1,
		ReferenceName: plumbing.NewBranchReferenceName(g.ref),
		Force:         true,
		Auth: &githttp.BasicAuth{
			Username: g.username,
			Password: g.password,
		},
	})
}

func (g *Git) GetLastFileCommitSHA(filePath string) (string, error) {
	repo, err := git.PlainOpen(g.clonePath)
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
