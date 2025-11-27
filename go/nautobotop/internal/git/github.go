package git

import (
	"context"
	"crypto/rsa"
	"encoding/pem"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/go-github/v55/github"
	"golang.org/x/oauth2"
)

type Github struct {
	appID         string
	orgName       string
	privateKeyPEM string
}

func NewGithub(appID, orgName, privateKeyPEM string) *Github {
	return &Github{
		appID:         appID,
		orgName:       orgName,
		privateKeyPEM: privateKeyPEM,
	}
}

func (g *Github) GetToken(ctx context.Context) (string, error) {
	_, token, err := g.getGHClientToken(ctx)
	return token, err
}

func (g *Github) parsePEMPrivateKey(pemStr string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(pemStr))
	if block == nil {
		return nil, fmt.Errorf("invalid PEM format")
	}
	return jwt.ParseRSAPrivateKeyFromPEM([]byte(pemStr))
}

func (g *Github) generateJWT(appID string, key *rsa.PrivateKey) (string, error) {
	now := time.Now()
	claims := jwt.RegisteredClaims{
		Issuer:    appID,
		IssuedAt:  jwt.NewNumericDate(now),
		ExpiresAt: jwt.NewNumericDate(now.Add(time.Minute * 10)),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	return token.SignedString(key)
}

func (g *Github) getGHClientToken(ctx context.Context) (*github.Client, string, error) {
	privateKey, err := g.parsePEMPrivateKey(g.privateKeyPEM)
	if err != nil {
		return nil, "", fmt.Errorf("error parsing private key: %v", err)
	}

	jwtToken, err := g.generateJWT(g.appID, privateKey)
	if err != nil {
		return nil, "", fmt.Errorf("error generating JWT: %v", err)
	}

	ghClient := github.NewTokenClient(ctx, jwtToken)
	installation, _, err := ghClient.Apps.FindOrganizationInstallation(ctx, g.orgName)
	if err != nil {
		return nil, "", fmt.Errorf("error listing installation for %s: %v", g.orgName, err)
	}

	installationID := installation.GetID()
	installationToken, _, err := ghClient.Apps.CreateInstallationToken(ctx, installationID, nil)
	if err != nil {
		return nil, "", fmt.Errorf("error getting installation token: %v", err)
	}

	token := installationToken.GetToken()
	tokenSrc := oauth2.StaticTokenSource(&oauth2.Token{AccessToken: token})
	oauthClient := oauth2.NewClient(ctx, tokenSrc)
	client := github.NewClient(oauthClient)

	return client, token, nil
}
