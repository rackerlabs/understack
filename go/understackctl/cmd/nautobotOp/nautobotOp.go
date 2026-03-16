package nautobotOp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/tools/clientcmd"
)

var (
	nautobotGVR = schema.GroupVersionResource{
		Group:    "sync.rax.io",
		Version:  "v1alpha1",
		Resource: "nautobots",
	}

	deploymentGVR = schema.GroupVersionResource{
		Group:    "apps",
		Version:  "v1",
		Resource: "deployments",
	}

	stdinReader = bufio.NewReader(os.Stdin)
)

type resyncOpts struct {
	crName       string
	operatorName string
}

type namespacedName struct {
	Namespace string
	Name      string
}

func (n namespacedName) String() string { return n.Namespace + "/" + n.Name }

func NewCmdNautobotOp() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "nautobotop",
		Short: "Nautobot Operator operations",
		RunE: func(cmd *cobra.Command, args []string) error {
			return cmd.Help()
		},
	}
	cmd.AddCommand(newResyncCmd())
	return cmd
}

func newResyncCmd() *cobra.Command {
	opts := &resyncOpts{}
	cmd := &cobra.Command{
		Use:   "resync",
		Short: "Force re-sync the Nautobot CRD resource",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runResync(opts)
		},
	}
	cmd.Flags().StringVarP(&opts.crName, "name", "n", "", "Name of the Nautobot CR (auto-detected if omitted)")
	cmd.Flags().StringVar(&opts.operatorName, "operator", "", "Operator deployment as namespace/name (auto-detected if omitted)")
	return cmd
}

func runResync(opts *resyncOpts) error {
	client, err := newDynamicClient()
	if err != nil {
		return fmt.Errorf("creating dynamic client: %w", err)
	}

	crName, err := resolveCRName(client, opts.crName)
	if err != nil {
		return err
	}

	if err := confirmWithUser(crName); err != nil {
		return err
	}

	if err := clearCRStatus(client, crName); err != nil {
		return err
	}

	operatorRef, err := resolveOperatorDeployment(client, opts.operatorName)
	if err != nil {
		return err
	}

	if err := rolloutRestartDeployment(client, operatorRef); err != nil {
		return err
	}

	log.Printf("resync complete: %s", crName)
	return nil
}

func resolveCRName(client dynamic.Interface, explicit string) (string, error) {
	if explicit != "" {
		return explicit, nil
	}

	list, err := client.Resource(nautobotGVR).List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		return "", fmt.Errorf("listing nautobot CRs: %w", err)
	}

	names := make([]string, len(list.Items))
	for i, item := range list.Items {
		names[i] = item.GetName()
	}

	selected, err := pickOne("nautobot CR", names)
	if err != nil {
		return "", err
	}
	log.Printf("using nautobot CR: %s", selected)
	return selected, nil
}

func resolveOperatorDeployment(client dynamic.Interface, explicit string) (namespacedName, error) {
	if explicit != "" {
		ref, err := parseNamespacedName(explicit)
		if err != nil {
			return namespacedName{}, fmt.Errorf("invalid --operator value: %w", err)
		}
		return ref, nil
	}

	list, err := client.Resource(deploymentGVR).Namespace("").List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		return namespacedName{}, fmt.Errorf("listing deployments: %w", err)
	}

	var candidates []namespacedName
	for _, item := range list.Items {
		if strings.Contains(item.GetName(), "nautobotop") {
			candidates = append(candidates, namespacedName{
				Namespace: item.GetNamespace(),
				Name:      item.GetName(),
			})
		}
	}

	labels := make([]string, len(candidates))
	for i, c := range candidates {
		labels[i] = c.String()
	}

	selected, err := pickOne("operator deployment", labels)
	if err != nil {
		return namespacedName{}, err
	}

	ref, _ := parseNamespacedName(selected)
	log.Printf("using operator deployment: %s", ref)
	return ref, nil
}

func parseNamespacedName(s string) (namespacedName, error) {
	parts := strings.SplitN(s, "/", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return namespacedName{}, fmt.Errorf("expected namespace/name format, got %q", s)
	}
	return namespacedName{Namespace: parts[0], Name: parts[1]}, nil
}

func clearCRStatus(client dynamic.Interface, crName string) error {
	log.Printf("clearing status: %s", crName)

	cr, err := client.Resource(nautobotGVR).Get(context.TODO(), crName, metav1.GetOptions{})
	if err != nil {
		return fmt.Errorf("getting nautobot %q: %w", crName, err)
	}

	cr.Object["status"] = map[string]any{}

	if _, err = client.Resource(nautobotGVR).UpdateStatus(context.TODO(), cr, metav1.UpdateOptions{}); err != nil {
		return fmt.Errorf("clearing status on %q: %w", crName, err)
	}
	return nil
}

func rolloutRestartDeployment(client dynamic.Interface, ref namespacedName) error {
	log.Printf("restarting deployment: %s", ref)

	patch, err := json.Marshal(map[string]any{
		"spec": map[string]any{
			"template": map[string]any{
				"metadata": map[string]any{
					"annotations": map[string]any{
						"understackctl/restartedAt": time.Now().Format(time.RFC3339),
					},
				},
			},
		},
	})
	if err != nil {
		return fmt.Errorf("marshalling restart patch: %w", err)
	}

	if _, err = client.Resource(deploymentGVR).Namespace(ref.Namespace).Patch(
		context.TODO(), ref.Name, types.MergePatchType, patch, metav1.PatchOptions{},
	); err != nil {
		return fmt.Errorf("restarting deployment %s: %w", ref, err)
	}
	return nil
}

func confirmWithUser(crName string) error {
	raw, err := clientcmd.NewNonInteractiveDeferredLoadingClientConfig(
		clientcmd.NewDefaultClientConfigLoadingRules(), nil,
	).RawConfig()
	if err != nil {
		return fmt.Errorf("loading kubeconfig: %w", err)
	}

	fmt.Printf("\n  Cluster:  %s\n  Resource: %s\n\n", raw.CurrentContext, crName)
	fmt.Print("  Proceed with resync? [y/N]: ")

	line, err := stdinReader.ReadString('\n')
	if err != nil {
		return fmt.Errorf("reading input: %w", err)
	}
	if strings.TrimSpace(strings.ToLower(line)) != "y" {
		return fmt.Errorf("aborted")
	}
	return nil
}

func pickOne(kind string, items []string) (string, error) {
	switch len(items) {
	case 0:
		return "", fmt.Errorf("no %s found in cluster", kind)
	case 1:
		return items[0], nil
	}

	fmt.Printf("Multiple %s resources found:\n", kind)
	for i, item := range items {
		fmt.Printf("  [%d] %s\n", i+1, item)
	}
	fmt.Print("Select number: ")

	line, err := stdinReader.ReadString('\n')
	if err != nil {
		return "", fmt.Errorf("reading input: %w", err)
	}

	var choice int
	if _, err := fmt.Sscanf(strings.TrimSpace(line), "%d", &choice); err != nil || choice < 1 || choice > len(items) {
		return "", fmt.Errorf("invalid selection: must be 1-%d", len(items))
	}
	return items[choice-1], nil
}

func newDynamicClient() (dynamic.Interface, error) {
	cfg, err := clientcmd.BuildConfigFromFlags("", clientcmd.RecommendedHomeFile)
	if err != nil {
		return nil, fmt.Errorf("loading kubeconfig: %w", err)
	}
	return dynamic.NewForConfig(cfg)
}
