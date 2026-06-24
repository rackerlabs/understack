package sync

import (
	"context"
	"fmt"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v3"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/extras"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/tenancy"
	"github.com/samber/lo"
	"go.yaml.in/yaml/v3"
)

type DeviceSync struct {
	client        *client.NautobotClient
	deviceSvc     *dcim.DeviceService
	deviceTypeSvc *dcim.DeviceTypeService
	locationSvc   *dcim.LocationService
	rackSvc       *dcim.RackService
	statusSvc     *dcim.StatusService
	roleSvc       *extras.RoleService
	tenantSvc     *tenancy.TenantService
}

func NewDeviceSync(nautobotClient *client.NautobotClient) *DeviceSync {
	return &DeviceSync{
		client:        nautobotClient.GetClient(),
		deviceSvc:     dcim.NewDeviceService(nautobotClient.GetClient()),
		deviceTypeSvc: dcim.NewDeviceTypeService(nautobotClient.GetClient()),
		locationSvc:   dcim.NewLocationService(nautobotClient.GetClient()),
		rackSvc:       dcim.NewRackService(nautobotClient),
		statusSvc:     dcim.NewStatusService(nautobotClient.GetClient()),
		roleSvc:       extras.NewRoleService(nautobotClient.GetClient()),
		tenantSvc:     tenancy.NewTenantService(nautobotClient.GetClient()),
	}
}

func (s *DeviceSync) SyncAll(ctx context.Context, data map[string]string) error {
	var devices models.Devices
	for key, f := range data {
		var yml models.Device
		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", "file: "+key+" error: "+err.Error())
			return err
		}
		devices.Devices = append(devices.Devices, yml)
	}

	for _, device := range devices.Devices {
		if err := s.syncSingleDevice(ctx, device); err != nil {
			return err
		}
	}

	s.deleteObsoleteDevices(ctx, devices)

	log.Info("SyncAllDevices Completed")
	return nil
}

func (s *DeviceSync) syncSingleDevice(ctx context.Context, device models.Device) error {
	existingDevice := s.deviceSvc.GetByID(ctx, device.ID)

	// Resolve device type reference (required)
	deviceTypeRef, err := s.buildDeviceTypeReference(ctx, device.DeviceType)
	if err != nil {
		return fmt.Errorf("failed to build device type reference for device %s: %w", device.Name, err)
	}

	// Resolve status reference (required)
	statusRef, err := s.buildStatusReference(ctx, device.Status)
	if err != nil {
		return fmt.Errorf("failed to build status reference for device %s: %w", device.Name, err)
	}

	// Resolve role reference (required)
	roleRef, err := s.buildRoleReference(ctx, device.Role)
	if err != nil {
		return fmt.Errorf("failed to build role reference for device %s: %w", device.Name, err)
	}

	// Resolve location reference (required)
	locationRef, err := s.buildLocationReference(ctx, device.Location)
	if err != nil {
		return fmt.Errorf("failed to build location reference for device %s: %w", device.Name, err)
	}

	deviceRequest := nb.WritableDeviceRequest{
		Id:         optionalID(device.ID),
		DeviceType: deviceTypeRef,
		Status:     statusRef,
		Role:       roleRef,
		Location:   locationRef,
		Comments:   nb.PtrString(device.Comments),
	}

	// Set name
	if device.Name != "" {
		deviceRequest.Name = *nb.NewNullableString(nb.PtrString(device.Name))
	}

	// Set serial
	if device.Serial != "" {
		deviceRequest.Serial = nb.PtrString(device.Serial)
	}

	// Set asset tag (optional)
	if device.AssetTag != "" {
		deviceRequest.AssetTag = *nb.NewNullableString(nb.PtrString(device.AssetTag))
	}

	// Set rack (optional)
	if device.Rack != "" {
		rackRef, err := s.buildRackReference(ctx, device.Rack)
		if err != nil {
			return fmt.Errorf("failed to build rack reference for device %s: %w", device.Name, err)
		}
		deviceRequest.Rack = rackRef
	}

	// Set position (optional)
	if device.Position > 0 {
		deviceRequest.Position = *nb.NewNullableInt32(nb.PtrInt32(int32(device.Position)))
	}

	// Set face (optional)
	if device.Face != "" {
		face, err := nb.NewRackFaceFromValue(device.Face)
		if err != nil {
			s.client.AddReport("syncDevice", "invalid face value, skipping face", "name", device.Name, "face", device.Face, "error", err.Error())
		} else {
			deviceRequest.Face = face
		}
	}

	// Set tenant (optional)
	if device.Tenant != "" {
		tenantRef, err := s.buildTenantReference(ctx, device.Tenant)
		if err != nil {
			return fmt.Errorf("failed to build tenant reference for device %s: %w", device.Name, err)
		}
		deviceRequest.Tenant = tenantRef
	}

	// Set platform (optional)
	if device.Platform != "" {
		platformRef := s.buildPlatformReference(device.Platform)
		deviceRequest.Platform = platformRef
	}

	if existingDevice.Id == nil {
		return s.createDevice(ctx, deviceRequest, device.Name)
	}

	if !helpers.CompareJSONFields(existingDevice, deviceRequest) {
		return s.updateDevice(ctx, *existingDevice.Id, deviceRequest, device.Name)
	}

	log.Info("device unchanged, skipping update", "name", device.Name)
	return nil
}

func (s *DeviceSync) createDevice(ctx context.Context, request nb.WritableDeviceRequest, name string) error {
	createdDevice, err := s.deviceSvc.Create(ctx, request)
	if err != nil || createdDevice == nil {
		return fmt.Errorf("failed to create device %s: %w", name, err)
	}
	log.Info("device created", "name", name)
	return nil
}

func (s *DeviceSync) updateDevice(ctx context.Context, id string, request nb.WritableDeviceRequest, name string) error {
	updatedDevice, err := s.deviceSvc.Update(ctx, id, request)
	if err != nil || updatedDevice == nil {
		return fmt.Errorf("failed to update device %s: %w", name, err)
	}
	log.Info("device updated", "name", name)
	return nil
}

func (s *DeviceSync) deleteObsoleteDevices(ctx context.Context, devices models.Devices) {
	desiredDevices := make(map[string]models.Device)
	for _, device := range devices.Devices {
		desiredDevices[device.Name] = device
	}

	existingDevices := s.deviceSvc.ListAll(ctx)
	existingMap := make(map[string]nb.Device, len(existingDevices))
	for _, device := range existingDevices {
		existingMap[device.GetName()] = device
	}

	obsoleteDevices := lo.OmitByKeys(existingMap, lo.Keys(desiredDevices))
	for _, obsoleteDevice := range obsoleteDevices {
		if obsoleteDevice.Id != nil {
			err := s.deviceSvc.Destroy(ctx, *obsoleteDevice.Id)
			if err != nil {
				log.Error("failed to delete obsolete device", "name", obsoleteDevice.GetName())
			}
		}
	}
}

func (s *DeviceSync) buildDeviceTypeReference(ctx context.Context, name string) (nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	deviceType := s.deviceTypeSvc.GetByName(ctx, name)
	if deviceType.Id == nil {
		return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{}, fmt.Errorf("device type '%s' not found in Nautobot", name)
	}
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*deviceType.Id), nil
}

func (s *DeviceSync) buildStatusReference(ctx context.Context, name string) (nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	status := s.statusSvc.GetByName(ctx, name)
	if status.Id == nil {
		return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{}, fmt.Errorf("status '%s' not found in Nautobot", name)
	}
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*status.Id), nil
}

func (s *DeviceSync) buildRoleReference(ctx context.Context, name string) (nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	role := s.roleSvc.GetByName(ctx, name)
	if role.Id == nil {
		return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{}, fmt.Errorf("role '%s' not found in Nautobot", name)
	}
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*role.Id), nil
}

func (s *DeviceSync) buildLocationReference(ctx context.Context, name string) (nb.ApprovalWorkflowStageResponseApprovalWorkflowStage, error) {
	location := s.locationSvc.GetByName(ctx, name)
	if location.Id == nil {
		return nb.ApprovalWorkflowStageResponseApprovalWorkflowStage{}, fmt.Errorf("location '%s' not found in Nautobot", name)
	}
	return helpers.BuildApprovalWorkflowStageResponseApprovalWorkflowStage(*location.Id), nil
}

func (s *DeviceSync) buildRackReference(ctx context.Context, name string) (nb.NullableApprovalWorkflowUser, error) {
	rack := s.rackSvc.GetByName(ctx, name)
	if rack.Id == nil {
		return nb.NullableApprovalWorkflowUser{}, fmt.Errorf("rack '%s' not found in Nautobot", name)
	}
	return helpers.BuildNullableApprovalWorkflowUser(*rack.Id), nil
}

func (s *DeviceSync) buildTenantReference(ctx context.Context, name string) (nb.NullableApprovalWorkflowUser, error) {
	tenant := s.tenantSvc.GetByName(ctx, name)
	if tenant.Id == nil {
		return nb.NullableApprovalWorkflowUser{}, fmt.Errorf("tenant '%s' not found in Nautobot", name)
	}
	return helpers.BuildNullableApprovalWorkflowUser(*tenant.Id), nil
}

func (s *DeviceSync) buildPlatformReference(platformID string) nb.NullableApprovalWorkflowUser {
	return helpers.BuildNullableApprovalWorkflowUser(platformID)
}
