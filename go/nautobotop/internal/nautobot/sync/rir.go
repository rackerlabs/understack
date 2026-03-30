package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/ipam"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/samber/lo"
	"go.yaml.in/yaml/v3"
)

type RirSync struct {
	client *client.NautobotClient
	rirSvc *ipam.RirService
}

func NewRirSync(nautobotClient *client.NautobotClient) *RirSync {
	return &RirSync{
		client: nautobotClient.GetClient(),
		rirSvc: ipam.NewRirService(nautobotClient),
	}
}

func (s *RirSync) SyncAll(ctx context.Context, data map[string]string) error {
	var rirs models.Rirs
	for key, f := range data {
		var yml []models.Rir
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		rirs.Rir = append(rirs.Rir, yml...)
	}

	for _, rir := range rirs.Rir {
		if err := s.syncSingleRir(ctx, rir); err != nil {
			return err
		}
	}
	s.deleteObsoleteRirs(ctx, rirs)
	return nil
}

func (s *RirSync) syncSingleRir(ctx context.Context, rir models.Rir) error {
	existingRir := s.rirSvc.GetByName(ctx, rir.Name)

	rirRequest := nb.RIRRequest{
		Name:      rir.Name,
		IsPrivate: nb.PtrBool(rir.IsPrivate),
	}
	if rir.Description != "" {
		rirRequest.Description = nb.PtrString(rir.Description)
	}

	if existingRir.Id == nil {
		return s.createRir(ctx, rirRequest)
	}
	if !helpers.CompareJSONFields(existingRir, rirRequest) {
		return s.updateRir(ctx, *existingRir.Id, rirRequest)
	}
	log.Info("rir unchanged, skipping update", "name", rirRequest.Name)
	return nil
}

func (s *RirSync) createRir(ctx context.Context, request nb.RIRRequest) error {
	created, err := s.rirSvc.Create(ctx, request)
	if err != nil || created == nil {
		return fmt.Errorf("failed to create rir %s: %w", request.Name, err)
	}
	log.Info("rir created", "name", request.Name)
	return nil
}

func (s *RirSync) updateRir(ctx context.Context, id string, request nb.RIRRequest) error {
	updated, err := s.rirSvc.Update(ctx, id, request)
	if err != nil || updated == nil {
		return fmt.Errorf("failed to update rir %s: %w", request.Name, err)
	}
	log.Info("rir updated", "name", request.Name)
	return nil
}

func (s *RirSync) deleteObsoleteRirs(ctx context.Context, rirs models.Rirs) {
	desired := make(map[string]models.Rir)
	for _, rir := range rirs.Rir {
		desired[rir.Name] = rir
	}

	existing := s.rirSvc.ListAll(ctx)
	existingMap := make(map[string]nb.RIR, len(existing))
	for _, rir := range existing {
		existingMap[rir.Name] = rir
	}

	obsolete := lo.OmitByKeys(existingMap, lo.Keys(desired))
	for _, rir := range obsolete {
		if rir.Id != nil {
			_ = s.rirSvc.Destroy(ctx, *rir.Id)
		}
	}
}
