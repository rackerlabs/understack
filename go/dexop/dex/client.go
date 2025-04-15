package dex

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"os"

	dexapi "github.com/dexidp/dex/api/v2"
	dexv1alpha1 "github.com/rackerlabs/understack/go/dexop/api/v1alpha1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
)

type DexManager struct {
	Client dexapi.DexClient
}

func (d *DexManager) init() {
	// start of dex iface
	client, err := newDexClient("127.0.0.1:5557", "./grpc_ca.crt", "./grpc_client.key", "./grpc_client.crt")
	if err != nil {
		// ctrl.Log.Error(err, "failed creating dex client")
	}
	d.Client = client
}

// Creates new Oauth2 client in Dex
func (d *DexManager) CreateOauth2Client(clientSpec *dexv1alpha1.Client) (*dexapi.CreateClientResp, error) {
	request := &dexapi.CreateClientReq{
		Client: &dexapi.Client{
			Id:           clientSpec.Spec.Name,
			Secret:       clientSpec.Spec.SecretName,
			RedirectUris: clientSpec.Spec.RedirectURIs,
			TrustedPeers: clientSpec.Spec.TrustedPeers,
			Public:       clientSpec.Spec.Public,
			Name:         clientSpec.Spec.Name,
			LogoUrl:      clientSpec.Spec.LogoUrl,
		},
	}

	return d.Client.CreateClient(context.TODO(), request)
}

// Deletes an Oauth2 client
func (d *DexManager) RemoveOauth2Client(clientSpec *dexv1alpha1.Client) (*dexapi.DeleteClientResp, error) {
	request := &dexapi.DeleteClientReq{
		Id: clientSpec.Spec.Name,
	}
	return d.Client.DeleteClient(context.TODO(), request)
}

// Patches/updates the Oauth2 client

func (d *DexManager) UpdateOauth2Client(clientSpec *dexv1alpha1.Client) (*dexapi.UpdateClientResp, error) {
	request := &dexapi.GetClientReq{
		Id: clientSpec.Spec.Name,
	}

	existing, err := d.Client.GetClient(context.TODO(), request)
	if err != nil {
		return nil, err
	}

	if existing == nil {
		return nil, fmt.Errorf("oauth2 client id: %s does not exist in Dex", clientSpec.Spec.Name)
	}

	if existing.Client.Secret != clientSpec.Spec.SecretName ||
		existing.Client.Public != clientSpec.Spec.Public {
		// dex does not support secret updates so it needs to be recreated
	}

	updateRequest := &dexapi.UpdateClientReq{
		Id:           clientSpec.Spec.Name,
		RedirectUris: clientSpec.Spec.RedirectURIs,
	}
	return d.Client.UpdateClient(context.TODO(), updateRequest)
}

func newDexClient(hostAndPort, caPath, clientKey, clientCrt string) (dexapi.DexClient, error) {
	cPool := x509.NewCertPool()
	caCert, err := os.ReadFile(caPath)
	if err != nil {
		return nil, fmt.Errorf("invalid CA crt file: %s", caPath)
	}
	if cPool.AppendCertsFromPEM(caCert) != true {
		return nil, fmt.Errorf("failed to parse CA crt")
	}

	clientCert, err := tls.LoadX509KeyPair(clientCrt, clientKey)
	if err != nil {
		return nil, fmt.Errorf("invalid client crt file: %s", clientCrt)
	}

	clientTLSConfig := &tls.Config{
		RootCAs:      cPool,
		Certificates: []tls.Certificate{clientCert},
	}
	creds := credentials.NewTLS(clientTLSConfig)

	conn, err := grpc.Dial(hostAndPort, grpc.WithTransportCredentials(creds))
	if err != nil {
		return nil, fmt.Errorf("dial: %v", err)
	}
	return dexapi.NewDexClient(conn), nil
}
