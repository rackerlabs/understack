package nautobotOp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/charmbracelet/log"
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

	operatorRef, err := resolveOperatorDeployment(client, opts.operatorName)
	if err != nil {
		return err
	}

	if err := confirmWithUser(crName); err != nil {
		return err
	}

	// Scale down the operator first to prevent the running pod from
	// racing with the new pod when we clear the CR status.
	if err := scaleDeployment(client, operatorRef, 0); err != nil {
		return err
	}

	if err := clearCRStatus(client, crName); err != nil {
		// Attempt to restore the operator on failure.
		_ = scaleDeployment(client, operatorRef, 1)
		return err
	}

	// Bring the operator back up so a single fresh pod reconciles.
	if err := scaleDeployment(client, operatorRef, 1); err != nil {
		return err
	}

	log.Info("resync complete", "cr", crName)
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
	log.Info("using nautobot CR", "name", selected)
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
	log.Info("using operator deployment", "ref", ref.String())
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
	log.Info("clearing status", "cr", crName)

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

func scaleDeployment(client dynamic.Interface, ref namespacedName, replicas int32) error {
	log.Info("scaling deployment", "ref", ref.String(), "replicas", replicas)

	patch, err := json.Marshal(map[string]any{
		"spec": map[string]any{
			"replicas": replicas,
		},
	})
	if err != nil {
		return fmt.Errorf("marshalling scale patch: %w", err)
	}

	if _, err = client.Resource(deploymentGVR).Namespace(ref.Namespace).Patch(
		context.TODO(), ref.Name, types.MergePatchType, patch, metav1.PatchOptions{},
	); err != nil {
		return fmt.Errorf("scaling deployment %s: %w", ref, err)
	}

	if replicas == 0 {
		if err := waitForScaleDown(client, ref); err != nil {
			return err
		}
	}
	return nil
}

func waitForScaleDown(client dynamic.Interface, ref namespacedName) error {
	log.Info("waiting for pods to terminate", "ref", ref.String())
	timeout := time.After(2 * time.Minute)
	tick := time.NewTicker(2 * time.Second)
	defer tick.Stop()

	for {
		select {
		case <-timeout:
			return fmt.Errorf("timed out waiting for %s to scale down", ref)
		case <-tick.C:
			dep, err := client.Resource(deploymentGVR).Namespace(ref.Namespace).Get(
				context.TODO(), ref.Name, metav1.GetOptions{},
			)
			if err != nil {
				return fmt.Errorf("checking deployment %s: %w", ref, err)
			}
			status, ok := dep.Object["status"].(map[string]any)
			if !ok {
				continue
			}
			readyReplicas, _ := status["readyReplicas"].(int64)
			if readyReplicas == 0 {
				log.Info("deployment scaled to 0", "ref", ref.String())
				return nil
			}
		}
	}
}

func confirmWithUser(crName string) error {
	raw, err := clientcmd.NewNonInteractiveDeferredLoadingClientConfig(
		clientcmd.NewDefaultClientConfigLoadingRules(), nil,
	).RawConfig()
	if err != nil {
		return fmt.Errorf("loading kubeconfig: %w", err)
	}

	fmt.Fprintln(os.Stderr)
	log.Warn("Double check the cluster and resource we are going to update")
	fmt.Fprintln(os.Stderr)
	fmt.Fprintf(os.Stderr, "  Cluster:  %s\n", raw.CurrentContext)
	fmt.Fprintf(os.Stderr, "  Resource: %s\n", crName)
	fmt.Fprintln(os.Stderr)
	fmt.Fprint(os.Stderr, "Proceed with resync? [y/N]: ")

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

	fmt.Fprintf(os.Stderr, "Multiple %s resources found:\n", kind)
	for i, item := range items {
		fmt.Fprintf(os.Stderr, "  [%d] %s\n", i+1, item)
	}
	fmt.Fprint(os.Stderr, "Select number: ")

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
