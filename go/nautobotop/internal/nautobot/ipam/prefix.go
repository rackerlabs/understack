package ipam

import (
	"context"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/cache"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
)

type PrefixService struct {
	client *client.NautobotClient
}

func NewPrefixService(nautobotClient *client.NautobotClient) *PrefixService {
	return &PrefixService{
		client: nautobotClient,
	}
}

func (s *PrefixService) Create(ctx context.Context, req nb.WritablePrefixRequest) (*nb.Prefix, error) {
	prefix, resp, err := s.client.APIClient.IpamAPI.IpamPrefixesCreate(ctx).WritablePrefixRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("createNewPrefix", "failed to create", "model", req.Prefix, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("CreatePrefix", "created prefix", prefix.Prefix)
	cache.AddToCollection(s.client.Cache, "prefixes", *prefix)

	return prefix, nil
}

func (s *PrefixService) GetByPrefix(ctx context.Context, prefix string) nb.Prefix {
	if p, ok := cache.FindByName(s.client.Cache, "prefixes", prefix, func(p nb.Prefix) string {
		return p.Prefix
	}); ok {
		return p
	}

	list, resp, err := s.client.APIClient.IpamAPI.IpamPrefixesList(ctx).Depth(2).Prefix([]string{prefix}).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("GetPrefixByPrefix", "failed to get", "prefix", prefix, "error", err.Error(), "response_body", bodyString)
		return nb.Prefix{}
	}
	if list == nil || len(list.Results) == 0 {
		return nb.Prefix{}
	}
	if list.Results[0].Id == nil {
		return nb.Prefix{}
	}

	return list.Results[0]
}

func (s *PrefixService) ListAll(ctx context.Context) []nb.Prefix {
	ids := s.client.GetChangeObjectIDS(ctx, "ipam.prefix")
	list, resp, err := s.client.APIClient.IpamAPI.IpamPrefixesList(ctx).Id(ids).Depth(2).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("ListAllPrefixes", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.Prefix{}
	}
	if list == nil || len(list.Results) == 0 {
		return []nb.Prefix{}
	}
	if list.Results[0].Id == nil {
		return []nb.Prefix{}
	}

	return list.Results
}

func (s *PrefixService) Update(ctx context.Context, id string, req nb.WritablePrefixRequest) (*nb.Prefix, error) {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("UpdatePrefix", "failed to check ownership", "id", id, "error", err.Error())
		return nil, err
	}
	if !owned {
		log.Warn("skipping update, object not created by user", "id", id, "user", s.client.Username)
		return nil, nil
	}

	prefix, resp, err := s.client.APIClient.IpamAPI.IpamPrefixesUpdate(ctx, id).WritablePrefixRequest(req).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("UpdatePrefix", "failed to update", "id", id, "model", req.Prefix, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Info("successfully updated prefix", "id", id, "model", prefix.GetPrefix())

	cache.UpdateInCollection(s.client.Cache, "prefixes", *prefix, func(p nb.Prefix) bool {
		return p.Id != nil && *p.Id == id
	})

	return prefix, nil
}

func (s *PrefixService) Destroy(ctx context.Context, id string) error {
	owned, err := s.client.IsCreatedByUser(ctx, id)
	if err != nil {
		s.client.AddReport("DestroyPrefix", "failed to check ownership", "id", id, "error", err.Error())
		return err
	}
	if !owned {
		log.Warn("skipping destroy, object not created by user", "id", id, "user", s.client.Username)
		return nil
	}

	resp, err := s.client.APIClient.IpamAPI.IpamPrefixesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := helpers.ReadResponseBody(resp)
		s.client.AddReport("DestroyPrefix", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	cache.RemoveFromCollection(s.client.Cache, "prefixes", func(p nb.Prefix) bool {
		return p.Id != nil && *p.Id == id
	})

	return nil
}
