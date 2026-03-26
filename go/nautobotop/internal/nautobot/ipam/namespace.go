package ipam

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type NamespaceService struct {
	client *client.NautobotClient
}

func NewNamespaceService(nautobotClient *client.NautobotClient) *NamespaceService {
	return &NamespaceService{
		client: nautobotClient,
	}
}

func (s *NamespaceService) Create(ctx context.Context, req nb.NamespaceRequest) (*nb.Namespace, error) {
	namespace, resp, err := s.client.APIClient.IpamAPI.IpamNamespacesCreate(ctx).NamespaceRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewNamespace", "failed to create", "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreateNamespace", "created namespace", namespace.Name)
	cache.AddToCollection(s.client.Cache, "namespaces", *namespace)

	return namespace, nil
}

func (s *NamespaceService) GetByName(ctx context.Context, name string) nb.Namespace {
	if ns, ok := cache.FindByName(s.client.Cache, "namespaces", name, func(n nb.Namespace) string {
		return n.Name
	}); ok {
		return ns
	}

	list, resp, err := s.client.APIClient.IpamAPI.IpamNamespacesList(ctx).Depth(2).Name([]string{name}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetNamespaceByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.Namespace{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Namespace{}
	}
	if list.Results[0].Id == nil {
		return nb.Namespace{}
	}

	return list.Results[0]
}

func (s *NamespaceService) ListAll(ctx context.Context) []nb.Namespace {
	ids := s.client.GetChangeObjectIDS(ctx, "ipam.namespace")
	list, resp, err := s.client.APIClient.IpamAPI.IpamNamespacesList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllNamespaces", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.Namespace{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.Namespace{}
	}
	if list.Results[0].Id == nil {
		return []nb.Namespace{}
	}

	return list.Results
}

func (s *NamespaceService) Update(ctx context.Context, id string, req nb.NamespaceRequest) (*nb.Namespace, error) {
	namespace, resp, err := s.client.APIClient.IpamAPI.IpamNamespacesUpdate(ctx, id).NamespaceRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdateNamespace", "failed to update", "id", id, "model", req.Name, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated namespace", "id", id, "model", namespace.GetName())

	cache.UpdateInCollection(s.client.Cache, "namespaces", *namespace, func(n nb.Namespace) bool {
		return n.Id != nil && *n.Id == id
	})

	return namespace, nil
}

func (s *NamespaceService) Destroy(ctx context.Context, id string) error {
	resp, err := s.client.APIClient.IpamAPI.IpamNamespacesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyNamespace", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "namespaces", func(n nb.Namespace) bool {
		return n.Id != nil && *n.Id == id
	})

	return nil
}
