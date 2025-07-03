package helmConfig

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/rackerlabs/understack/go/understackctl/helpers"

	"github.com/gookit/goutil/envutil"
	"github.com/gookit/goutil/fsutil"
	"github.com/spf13/cobra"
)

func NewCmdHelmConfig() *cobra.Command {
	return &cobra.Command{
		Use:   "helm-config",
		Short: "Create helm config for individual services",
		Long:  "",
		Run:   helmConfigGen,
	}
}
func helmConfigGen(cmd *cobra.Command, args []string) {
	functions := []func() error{
		dex,
		glance,
		ironic,
		rook,
	}
	for _, fn := range functions {
		if err := fn(); err != nil {
			fmt.Printf("Error helmConfigGen: %v\n", err)
			os.Exit(1)
		}
	}
}

func dex() error {
	template := `config:
    staticClients:
      - id: nautobot
        secretEnv: NAUTOBOT_SSO_CLIENT_SECRET
        name: "Undercloud Nautobot"
        redirectURIs:
          - "https://nautobot.{{ .DNS_ZONE }}/complete/oidc/"
      - id: argo
        secretEnv: ARGO_SSO_CLIENT_SECRET
        name: "Undercloud Argo"
        redirectURIs:
          - "https://workflows.{{ .DNS_ZONE }}/oauth2/callback"
      - id: argocd
        secretEnv: ARGOCD_SSO_CLIENT_SECRET
        name: "Undercloud ArgoCD"
        redirectURIs:
          - "https://argocd.{{ .DNS_ZONE }}/auth/callback"`

	vars := map[string]any{
		"DNS_ZONE": envutil.Getenv("DNS_ZONE"),
	}

	data, err := helpers.TemplateHelper(template, vars)
	if err != nil {
		return fmt.Errorf("failed to render template: %w", err)
	}

	filePath := filepath.Join(
		envutil.Getenv("DEPLOY_NAME"),
		"helm",
		"dex.yaml",
	)

	if err := fsutil.WriteFile(filePath, data, os.ModePerm); err != nil {
		return fmt.Errorf("failed to write %s: %w", filePath, err)
	}
	return nil
}

func glance() error {
	template := `volume:
    class_name: csi-cinder-sc-delete
    size: 20Gi`

	filePath := filepath.Join(
		envutil.Getenv("DEPLOY_NAME"),
		"helm",
		"glance.yaml",
	)

	if err := fsutil.WriteFile(filePath, template, os.ModePerm); err != nil {
		return fmt.Errorf("failed to write %s: %w", filePath, err)
	}

	return nil
}

func ironic() error {
	template := `labels:
    conductor:
      node_selector_key: "understack.node.cluster.x-k8s.io/ironic-role"
      node_selector_value: conductor

  conductor:
    initContainers:
      - name: create-tmpdir
        image: docker.io/openstackhelm/heat:2024.2-ubuntu_jammy
        imagePullPolicy: IfNotPresent
        command: [bash]
        args:
          - "-c"
          - "mkdir -p /var/lib/openstack-helm/tmp"
        volumeMounts:
          - name: pod-data
            mountPath: /var/lib/openstack-helm`

	filePath := filepath.Join(
		envutil.Getenv("DEPLOY_NAME"),
		"helm",
		"ironic.yaml",
	)

	if err := fsutil.WriteFile(filePath, template, os.ModePerm); err != nil {
		return fmt.Errorf("failed to write %s: %w", filePath, err)
	}

	return nil
}

func rook() error {
	template := `cephClusterSpec:
    mon:
      # Set the number of mons to be started. Generally recommended to be 3.
      # For highest availability, an odd number of mons should be specified.
      count: 2
      # The mons should be on unique nodes. For production, at least 3 nodes are recommended for this reason.
      # Mons should only be allowed on the same node for test environments where data loss is acceptable.
      allowMultiplePerNode: false

    mgr:
      # When higher availability of the mgr is needed, increase the count to 2.
      # In that case, one mgr will be active and one in standby. When Ceph updates which
      # mgr is active, Rook will update the mgr services to match the active mgr.
      count: 2
      allowMultiplePerNode: false

    storage:
      useAllDevices: false
      useAllNodes: true
      deviceFilter: "vdb"
    resources:
      mgr:
        limits:
          memory: "1Gi"
        requests:
          cpu: "0"
          memory: "512Mi"
      mon:
        limits:
          memory: "2Gi"
        requests:
          cpu: "0"
          memory: "1Gi"
      osd:
        limits:
          memory: "4Gi"
        requests:
          cpu: "0"
          memory: "4Gi"
      prepareosd:
        # limits: It is not recommended to set limits on the OSD prepare job
        #         since it's a one-time burst for memory that must be allowed to
        #         complete without an OOM kill.  Note however that if a k8s
        #         limitRange guardrail is defined external to Rook, the lack of
        #         a limit here may result in a sync failure, in which case a
        #         limit should be added.  1200Mi may suffice for up to 15Ti
        #         OSDs ; for larger devices 2Gi may be required.
        #         cf. https://github.com/rook/rook/pull/11103
        requests:
          cpu: "0"
          memory: "50Mi"
      mgr-sidecar:
        limits:
          memory: "100Mi"
        requests:
          cpu: "0"
          memory: "40Mi"
      crashcollector:
        limits:
          memory: "60Mi"
        requests:
          cpu: "0"
          memory: "60Mi"
      logcollector:
        limits:
          memory: "1Gi"
        requests:
          cpu: "0"
          memory: "100Mi"
      cleanup:
        limits:
          memory: "1Gi"
        requests:
          cpu: "0"
          memory: "100Mi"
      exporter:
        limits:
          memory: "128Mi"
        requests:
          cpu: "0"
          memory: "50Mi"`

	filePath := filepath.Join(
		envutil.Getenv("DEPLOY_NAME"),
		"helm",
		"rook-cluster.yaml",
	)

	if err := fsutil.WriteFile(filePath, template, os.ModePerm); err != nil {
		return fmt.Errorf("failed to write %s: %w", filePath, err)
	}

	return nil
}
