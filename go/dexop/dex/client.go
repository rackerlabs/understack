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
	"google.golang.org/grpc/credentials/insecure"
)

type DexManager struct {
	Client dexapi.DexClient
	Issuer string
}

// Creates new Oauth2 client in Dex
func (d *DexManager) CreateOauth2Client(clientSpec *dexv1alpha1.Client) (*dexapi.CreateClientResp, error) {
	request := &dexapi.CreateClientReq{
		Client: &dexapi.Client{
			Id:           clientSpec.Spec.Name,
			Secret:       clientSpec.Spec.SecretValue,
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
func (d *DexManager) RemoveOauth2Client(clientId string) (*dexapi.DeleteClientResp, error) {
	request := &dexapi.DeleteClientReq{
		Id: clientId,
	}
	return d.Client.DeleteClient(context.TODO(), request)
}

func (d *DexManager) GetOauth2Client(clientId string) (*dexapi.GetClientResp, error) {
	request := &dexapi.GetClientReq{
		Id: clientId,
	}
	return d.Client.GetClient(context.TODO(), request)
}

// Patches/updates the Oauth2 client

func (d *DexManager) UpdateOauth2Client(clientSpec *dexv1alpha1.Client) error {
	existing, err := d.GetOauth2Client(clientSpec.Spec.Name)
	if err != nil {
		return err
	}

	if existing == nil {
		return fmt.Errorf("oauth2 client id: %s does not exist in Dex", clientSpec.Spec.Name)
	}

	if existing.Client.Secret != clientSpec.Spec.SecretValue ||
		existing.Client.Public != clientSpec.Spec.Public {
		// dex does not support secret updates so it needs to be recreated
		_, err = d.RemoveOauth2Client(clientSpec.Spec.Name)
		if err != nil {
			return err
		}
		_, err := d.CreateOauth2Client(clientSpec)
		if err != nil {
			return err
		}
	}

	updateRequest := &dexapi.UpdateClientReq{
		Id:           clientSpec.Spec.Name,
		RedirectUris: clientSpec.Spec.RedirectURIs,
		TrustedPeers: clientSpec.Spec.TrustedPeers,
		LogoUrl:      clientSpec.Spec.LogoUrl,
		Name:         clientSpec.Spec.Name,
	}
	_, err = d.Client.UpdateClient(context.TODO(), updateRequest)
	return err
}

func (d *DexManager) GetIssuer() (string, error) {
	// fallback for dex versions that don't support Discovery over GRPC
	if d.Issuer != "" {
		return d.Issuer, nil
	}

	result, err := d.Client.GetDiscovery(context.TODO(), &dexapi.DiscoveryReq{})
	if err != nil {
		return "", err
	}
	return result.GetIssuer(), nil
}

func newDexClient(hostAndPort, caPath, clientKey, clientCrt string) (dexapi.DexClient, error) {
	cPool := x509.NewCertPool()
	caCert, err := os.ReadFile(caPath)
	if err != nil {
		return nil, fmt.Errorf("invalid CA crt file (%s): %w", caPath, err)
	}
	if !cPool.AppendCertsFromPEM(caCert) {
		return nil, fmt.Errorf("failed to parse CA crt")
	}

	clientCert, err := tls.LoadX509KeyPair(clientCrt, clientKey)
	if err != nil {
		return nil, fmt.Errorf("invalid client crt(%s) or key(%s) file: %w", clientCrt, clientKey, err)
	}

	clientTLSConfig := &tls.Config{
		RootCAs:      cPool,
		Certificates: []tls.Certificate{clientCert},
	}
	creds := credentials.NewTLS(clientTLSConfig)

	conn, err := grpc.NewClient(hostAndPort, grpc.WithTransportCredentials(creds))
	if err != nil {
		return nil, fmt.Errorf("dial: %v", err)
	}
	return dexapi.NewDexClient(conn), nil
}

func NewInsecureTestManager(grpcAddr string) (*DexManager, error) {
	// Establish gRPC connection for tests to use
	grpcConn, err := grpc.NewClient(grpcAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}
	return &DexManager{Client: dexapi.NewDexClient(grpcConn), Issuer: "http://127.0.0.1:15556/dex"}, nil
}

func NewDexManager(host, caCert, clientKey, clientCert, issuer string) (*DexManager, error) {
	client, err := newDexClient(host, caCert, clientKey, clientCert)
	if err != nil {
		return nil, fmt.Errorf("failed creating dex client: %w", err)
	}
	return &DexManager{Client: client, Issuer: issuer}, nil
}
