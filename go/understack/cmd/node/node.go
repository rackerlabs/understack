package node

import (
	"context"
	"os"

	"github.com/rackerlabs/understack/go/understack/helpers"

	"github.com/charmbracelet/log"

	"github.com/spf13/cobra"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func NewCmdNode() *cobra.Command {
	return &cobra.Command{
		Use:   "node-update",
		Short: "Will update k8s cluster node with labels and tags",
		Long:  "Will update k8s cluster node with labels and tags",
		Run:   updateNode,
	}
}

func updateNode(cmd *cobra.Command, args []string) {
	if err := labelNodes(); err != nil {
		log.Error("Failed to label nodes", "err", err)
		os.Exit(1)
	}
}

func labelNodes() error {
	clientset := helpers.KubeClientSet()

	nodes, err := clientset.CoreV1().Nodes().List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		return err
	}

	for _, node := range nodes.Items {
		if _, exists := node.Labels["openstack-control-plane"]; exists {
			log.Info("Node already labeled. Skipping", node.Name, node.Labels["openstack-control-plane"])
			continue
		}

		log.Info("Labeling node " + node.Name)

		node.Labels["openstack-control-plane"] = "enabled"

		// Update the node
		_, err := clientset.CoreV1().Nodes().Update(context.TODO(), &node, metav1.UpdateOptions{})
		if err != nil {
			log.Error("Failed to label node", node.Name, err)
		} else {
			log.Info("Successfully labeled node", node.Name)
		}
	}

	return nil
}
