package deploy

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/charmbracelet/log"
	"github.com/google/go-containerregistry/pkg/authn"
	"github.com/google/go-containerregistry/pkg/name"
	"github.com/google/go-containerregistry/pkg/v1/remote"
	"github.com/spf13/cobra"
)

var (
	imageTagRe = regexp.MustCompile(`([^\s"']+/understack/[^:]+):v[0-9]+\.[0-9]+\.[0-9]+(?:@sha256:[a-f0-9]+)?`)
	refTagRe   = regexp.MustCompile(`(\?ref=)v[0-9]+\.[0-9]+\.[0-9]+`)
)

func newCmdDeployImageSet() *cobra.Command {
	var noDigest bool

	cmd := &cobra.Command{
		Use:   "image-set <cluster-name> <version>",
		Short: "Update UnderStack image tags to a new version",
		Long: `Walk all YAML files in the cluster directory and replace UnderStack image
references of the form .*/understack/.*:vX.Y.Z[@sha256:...] with the given
version tag. Also updates ?ref=vX.Y.Z in all kustomization.yaml files.

By default the sha256 digest is resolved from the registry and pinned
alongside the tag. Use --no-digest to write the tag only.`,
		Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			return runDeployImageSet(args[0], args[1], noDigest)
		},
	}

	cmd.Flags().BoolVar(&noDigest, "no-digest", false, "Write tag only, skip sha256 digest lookup")

	return cmd
}

func runDeployImageSet(clusterName, version string, noDigest bool) error {
	if !strings.HasPrefix(version, "v") {
		version = "v" + version
	}

	digestCache := map[string]string{}

	updated := 0
	err := filepath.WalkDir(clusterName, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		ext := strings.ToLower(filepath.Ext(path))
		if ext != ".yaml" && ext != ".yml" {
			return nil
		}

		data, err := os.ReadFile(path)
		if err != nil {
			return fmt.Errorf("failed to read %s: %w", path, err)
		}

		original := string(data)
		result := replaceImageTags(original, version, noDigest, digestCache)
		if filepath.Base(path) == "kustomization.yaml" {
			result = refTagRe.ReplaceAllString(result, "${1}"+version)
		}

		if result == original {
			return nil
		}

		if err := os.WriteFile(path, []byte(result), d.Type().Perm()); err != nil {
			return fmt.Errorf("failed to write %s: %w", path, err)
		}

		log.Infof("Updated %s", path)
		updated++
		return nil
	})
	if err != nil {
		return err
	}

	log.Infof("image-set complete: %d file(s) updated to %s", updated, version)
	return nil
}

// replaceImageTags rewrites all understack image references in content to the
// given version, optionally pinning the sha256 digest fetched from the registry.
func replaceImageTags(content, version string, noDigest bool, digestCache map[string]string) string {
	return imageTagRe.ReplaceAllStringFunc(content, func(match string) string {
		groups := imageTagRe.FindStringSubmatch(match)
		imageBase := groups[1]
		newRef := imageBase + ":" + version

		if noDigest {
			return newRef
		}

		if digest, ok := digestCache[newRef]; ok {
			if digest == "" {
				return newRef
			}
			return newRef + "@" + digest
		}

		digest, err := resolveDigest(newRef)
		if err != nil {
			log.Warnf("Could not resolve digest for %s: %v", newRef, err)
			digestCache[newRef] = ""
			return newRef
		}

		log.Debugf("Resolved %s -> %s", newRef, digest)
		digestCache[newRef] = digest
		return newRef + "@" + digest
	})
}

// resolveDigest fetches the manifest digest for an image reference from the
// registry using a lightweight HEAD request (no image data is pulled).
func resolveDigest(imageRef string) (string, error) {
	ref, err := name.ParseReference(imageRef)
	if err != nil {
		return "", fmt.Errorf("invalid image reference %q: %w", imageRef, err)
	}

	desc, err := remote.Head(ref, remote.WithAuthFromKeychain(authn.DefaultKeychain))
	if err != nil {
		return "", fmt.Errorf("registry lookup failed: %w", err)
	}

	return desc.Digest.String(), nil
}
