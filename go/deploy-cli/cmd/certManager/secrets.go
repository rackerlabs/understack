package certManager

import (
	"os"

	"github.com/rackerlabs/understack/go/deploy-cli/cmd"
	"github.com/rackerlabs/understack/go/deploy-cli/helpers"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/fsutil"

	"github.com/spf13/cobra"
)

func init() {
	cmd.RootCmd.AddCommand(CertManager)
}

var CertManager = &cobra.Command{
	Use:   "certmanager-secrets",
	Short: "Generate certmanager-secrets secrets",
	Long:  "",
	Run:   certManagerGen,
}

func certManagerGen(cmd *cobra.Command, args []string) {
	clusterIssuer()
}

var clusterIssuerTemplate = `---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: understack-cluster-issuer
  annotations:
    argocd.argoproj.io/sync-wave: "5"
spec:
  acme:
    email: undercloud-dev+uc-iad3-dev@rackspace.com
    privateKeySecretRef:
      name: letsencrypt-prod
    server: https://acme-v02.api.letsencrypt.org/directory
    solvers:
      - http01:
          ingress:
            ingressClassName: nginx
        selector:
          matchLabels:
            authorizeWith: http
      - dns01:
          webhook:
            groupName: acme.undercloud.rackspace.net
            solverName: rackspace
            config:
              authSecretRef: cert-manager-webhook-rackspace-creds
              domainName: dev.undercloud.rackspace.net
`

// credGen prints out the cli version number
func clusterIssuer() {
	filePath := helpers.GetManifestPathToService("cert-manager") + "/cluster-issuer.yaml"
	err := fsutil.WriteFile(filePath, clusterIssuerTemplate, os.ModePerm)
	if err != nil {
		log.Fatal("error in kustomization.yaml file", "err", err)
		os.Exit(1)
	}
	helpers.UpdateKustomizeFile(helpers.GetManifestPathToService("cert-manager"))
}
