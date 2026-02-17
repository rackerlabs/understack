package client

import (
	"context"

	"github.com/charmbracelet/log"
)

func (n *NautobotClient) PreLoadCacheForLookup(ctx context.Context) error {
	if list, _, err := n.APIClient.ExtrasAPI.ExtrasStatusesList(ctx).Depth(2).Execute(); err == nil && list != nil {
		n.Cache.SetCollection("statuses", list.Results)
		log.Info("pre-load statuses cache", "count", len(list.Results))
	}

	if list, _, err := n.APIClient.DcimAPI.DcimLocationTypesList(ctx).Depth(2).Execute(); err == nil && list != nil {
		n.Cache.SetCollection("locationtypes", list.Results)
		log.Info("pre-load location types cache", "count", len(list.Results))
	}

	if list, _, err := n.APIClient.DcimAPI.DcimLocationsList(ctx).Depth(2).Execute(); err == nil && list != nil {
		n.Cache.SetCollection("locations", list.Results)
		log.Info("pre-load locations cache", "count", len(list.Results))
	}

	if list, _, err := n.APIClient.DcimAPI.DcimRackGroupsList(ctx).Depth(2).Execute(); err == nil && list != nil {
		n.Cache.SetCollection("rackgroups", list.Results)
		log.Info("pre-load rack groups cache", "count", len(list.Results))
	}

	if list, _, err := n.APIClient.DcimAPI.DcimRacksList(ctx).Depth(2).Execute(); err == nil && list != nil {
		n.Cache.SetCollection("racks", list.Results)
		log.Info("pre-load racks cache", "count", len(list.Results))
	}

	if list, _, err := n.APIClient.DcimAPI.DcimManufacturersList(ctx).Depth(2).Execute(); err == nil && list != nil {
		n.Cache.SetCollection("manufacturers", list.Results)
		log.Info("pre-load manufacturers cache", "count", len(list.Results))
	}

	if list, _, err := n.APIClient.DcimAPI.DcimDeviceTypesList(ctx).Depth(2).Execute(); err == nil && list != nil {
		n.Cache.SetCollection("devicetypes", list.Results)
		log.Info("pre-load device types cache", "count", len(list.Results))
	}

	return nil
}
