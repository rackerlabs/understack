package sync

import (
	"context"
	"fmt"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/client"

	"github.com/charmbracelet/log"
	nb "github.com/nautobot/go-nautobot/v2"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/dcim/templates"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/helpers"
	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/models"
	"github.com/samber/lo"
	"go.yaml.in/yaml/v3"
)

type DeviceTypeSync struct {
	client                 *client.NautobotClient
	manufacturerSvc        *dcim.ManufacturerService
	deviceTypeSvc          *dcim.DeviceTypeService
	consolePortTemplateSvc *templates.ConsolePortTemplateService
	powerPortTemplateSvc   *templates.PowerPortTemplateService
	interfaceTemplateSvc   *templates.InterfaceTemplateService
	moduleBayTemplateSvc   *templates.ModuleBayTemplateService
}

func NewDeviceTypeSync(nautobotClient *client.NautobotClient) *DeviceTypeSync {
	return &DeviceTypeSync{
		client:                 nautobotClient.GetClient(),
		manufacturerSvc:        dcim.NewManufacturerService(nautobotClient.GetClient()),
		deviceTypeSvc:          dcim.NewDeviceTypeService(nautobotClient.GetClient()),
		consolePortTemplateSvc: templates.NewConsolePortTemplateService(nautobotClient.GetClient()),
		powerPortTemplateSvc:   templates.NewPowerPortTemplateService(nautobotClient.GetClient()),
		interfaceTemplateSvc:   templates.NewInterfaceTemplateService(nautobotClient.GetClient()),
		moduleBayTemplateSvc:   templates.NewModuleBayTemplateService(nautobotClient.GetClient()),
	}
}

func (s *DeviceTypeSync) SyncAll(ctx context.Context, data map[string]string) error {
	var deviceTypes models.DeviceTypes
	for _, f := range data {

		var yml models.DeviceType

		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			s.client.AddReport("yamlFailed", err.Error())
			return err
		}
		deviceTypes.DeviceTypes = append(deviceTypes.DeviceTypes, yml)

		manufacturer := s.manufacturerSvc.GetByName(context.Background(), yml.Manufacturer)
		if manufacturer.Id == "" {
			cm, err := s.manufacturerSvc.Create(context.Background(), nb.ManufacturerRequest{
				Name:        yml.Manufacturer,
				Description: nb.PtrString(yml.Manufacturer),
			})
			if err != nil || cm == nil {
				return fmt.Errorf("failed to create manufacturer %s: %w", yml.Manufacturer, err)
			}
			manufacturer = *cm
		}

		deviceType := s.deviceTypeSvc.GetByName(context.Background(), yml.Model)
		deviceTypeRequest := nb.WritableDeviceTypeRequest{
			Model:        yml.Model,
			PartNumber:   nb.PtrString(yml.PartNumber),
			UHeight:      nb.PtrInt32(int32(yml.UHeight)),
			IsFullDepth:  nb.PtrBool(yml.IsFullDepth),
			Comments:     nb.PtrString(yml.Comments),
			Manufacturer: *helpers.BuildBulkWritableCableRequestStatus(manufacturer.Id),
		}

		if deviceType.Id == "" {
			createdDt, err := s.deviceTypeSvc.Create(context.Background(), deviceTypeRequest)
			if err != nil || createdDt == nil {
				return fmt.Errorf("failed to create device type %s: %w", yml.Model, err)
			}
			deviceType = *createdDt
		} else if !helpers.CompareJSONFields(deviceType, deviceTypeRequest) {
			updatedDt, err := s.deviceTypeSvc.Update(ctx, deviceType.Id, deviceTypeRequest)
			if err != nil || updatedDt == nil {
				return fmt.Errorf("failed to update device type %s: %w", yml.Model, err)
			}
			deviceType = *updatedDt
		} else {
			log.Info("device type unchanged, skipping update", "model", yml.Model)
		}

		s.syncInterfaceTemplates(ctx, yml, deviceType)
		s.syncConsolePortTemplates(ctx, yml, deviceType)
		s.syncPowerPortTemplates(ctx, yml, deviceType)
		s.syncModuleBayTemplates(ctx, yml, deviceType)
	}

	desiredDeviceTypes := make(map[string]models.DeviceType)
	for _, deviceType := range deviceTypes.DeviceTypes {
		desiredDeviceTypes[deviceType.Model] = deviceType
	}

	existingDeviceTypes := s.deviceTypeSvc.ListAll(ctx)
	existingMap := make(map[string]nb.DeviceType, len(existingDeviceTypes))
	for _, template := range existingDeviceTypes {
		existingMap[template.Model] = template
	}
	obsoleteDeviceTypes := lo.OmitByKeys(existingMap, lo.Keys(desiredDeviceTypes))
	for _, obsoleteDeviceType := range obsoleteDeviceTypes {
		_ = s.deviceTypeSvc.Destroy(ctx, obsoleteDeviceType.Id)
	}

	log.Info("SyncAllDevice Completed")
	return nil
}

func (s *DeviceTypeSync) syncPowerPortTemplates(ctx context.Context, yml models.DeviceType, deviceType nb.DeviceType) {
	// Build map of desired power ports from YAML configuration
	desiredPorts := make(map[string]models.PowerPort)
	for _, port := range yml.PowerPorts {
		desiredPorts[port.Name] = port
	}

	// Build map of existing power port templates from Nautobot
	existingTemplates := s.powerPortTemplateSvc.ListByDeviceType(ctx, deviceType.Id)
	existingMap := make(map[string]nb.PowerPortTemplate)
	for _, template := range existingTemplates {
		existingMap[template.Name] = template
	}

	// Process each desired power port: create new or update existing
	for name, desiredPort := range desiredPorts {
		powerPortTypeChoice, _ := nb.NewPowerPortTypeChoicesFromValue(desiredPort.Type)

		var maximumDraw nb.NullableInt32
		if desiredPort.MaximumDraw > 0 {
			maximumDraw = *nb.NewNullableInt32(nb.PtrInt32(int32(desiredPort.MaximumDraw)))
		}

		var allocatedDraw nb.NullableInt32
		if desiredPort.AllocatedDraw > 0 {
			allocatedDraw = *nb.NewNullableInt32(nb.PtrInt32(int32(desiredPort.AllocatedDraw)))
		}

		templateRequest := nb.WritablePowerPortTemplateRequest{
			Name: desiredPort.Name,
			Type: &nb.PatchedWritablePowerPortTemplateRequestType{
				PowerPortTypeChoices: powerPortTypeChoice,
			},
			MaximumDraw:   maximumDraw,
			AllocatedDraw: allocatedDraw,
			DeviceType:    helpers.BuildNullableBulkWritableCircuitRequestTenant(deviceType.Id),
		}

		if existingTemplate, exists := existingMap[name]; !exists {
			_, _ = s.powerPortTemplateSvc.Create(ctx, templateRequest)
		} else if !helpers.CompareJSONFields(existingTemplate, templateRequest) {
			_, _ = s.powerPortTemplateSvc.Update(ctx, existingTemplate.Id, templateRequest)
		} else {
			log.Info("power port template unchanged, skipping update", "name", templateRequest.Name, "deviceTypeId", deviceType.Id, "deviceTypeName", deviceType.Display)
		}
	}

	obsoletes := lo.OmitByKeys(existingMap, lo.Keys(desiredPorts))
	for _, obsolete := range obsoletes {
		_ = s.powerPortTemplateSvc.Destroy(ctx, obsolete.Id)
	}
}

func (s *DeviceTypeSync) syncConsolePortTemplates(ctx context.Context, yml models.DeviceType, deviceType nb.DeviceType) {
	// Build map of desired console ports from YAML configuration
	desiredPorts := make(map[string]models.ConsolePort)
	for _, port := range yml.ConsolePorts {
		desiredPorts[port.Name] = port
	}

	existingTemplates := s.consolePortTemplateSvc.ListByDeviceType(ctx, deviceType.Id)
	existingMap := make(map[string]nb.ConsolePortTemplate)
	for _, template := range existingTemplates {
		existingMap[template.Name] = template
	}

	for name, desiredPort := range desiredPorts {
		consolePortTypeChoice, _ := nb.NewConsolePortTypeChoicesFromValue(desiredPort.Type)
		templateRequest := nb.WritableConsolePortTemplateRequest{
			Name: name,
			Type: &nb.PatchedWritableConsolePortTemplateRequestType{
				ConsolePortTypeChoices: consolePortTypeChoice,
			},
			DeviceType: helpers.BuildNullableBulkWritableCircuitRequestTenant(deviceType.Id),
		}
		if existingTemplate, exists := existingMap[name]; !exists {
			_, _ = s.consolePortTemplateSvc.Create(ctx, templateRequest)
		} else if !helpers.CompareJSONFields(existingTemplate, templateRequest) {
			_, _ = s.consolePortTemplateSvc.Update(ctx, existingTemplate.Id, templateRequest)
		} else {
			log.Info("console port template unchanged, skipping update", "name", templateRequest.Name, "deviceTypeId", deviceType.Id, "deviceTypeName", deviceType.Display)
		}
	}
	obsoletes := lo.OmitByKeys(existingMap, lo.Keys(desiredPorts))
	for _, obsolete := range obsoletes {
		_ = s.consolePortTemplateSvc.Destroy(ctx, obsolete.Id)
	}
}

func (s *DeviceTypeSync) syncInterfaceTemplates(ctx context.Context, yml models.DeviceType, deviceType nb.DeviceType) {
	// Build map of desired console ports from YAML configuration
	desiredInterfaceTemplate := make(map[string]models.Interface)
	for _, interfaceTmpl := range yml.Interfaces {
		desiredInterfaceTemplate[interfaceTmpl.Name] = interfaceTmpl
	}

	existingTemplates := s.interfaceTemplateSvc.ListByDeviceType(ctx, deviceType.Id)
	existingMap := make(map[string]nb.InterfaceTemplate)
	for _, template := range existingTemplates {
		existingMap[template.Name] = template
	}
	for name, interfaceTmpl := range desiredInterfaceTemplate {
		interfaceTemplateChoice, _ := nb.NewInterfaceTypeChoicesFromValue(interfaceTmpl.Type)

		templateRequest := nb.WritableInterfaceTemplateRequest{
			Name:       name,
			Type:       *interfaceTemplateChoice,
			MgmtOnly:   nb.PtrBool(interfaceTmpl.MgmtOnly),
			DeviceType: helpers.BuildNullableBulkWritableCircuitRequestTenant(deviceType.Id),
		}

		if existingTemplate, exists := existingMap[name]; !exists {
			_, _ = s.interfaceTemplateSvc.Create(ctx, templateRequest)
		} else if !helpers.CompareJSONFields(existingTemplate, templateRequest) {
			_, _ = s.interfaceTemplateSvc.Update(ctx, existingTemplate.Id, templateRequest)
		} else {
			log.Info("interface template unchanged, skipping update", "name", templateRequest.Name, "deviceTypeId", deviceType.Id, "deviceTypeName", deviceType.Display)
		}
	}
	obsoletes := lo.OmitByKeys(existingMap, lo.Keys(desiredInterfaceTemplate))
	for _, obsolete := range obsoletes {
		_ = s.interfaceTemplateSvc.Destroy(ctx, obsolete.Id)
	}
}

func (s *DeviceTypeSync) syncModuleBayTemplates(ctx context.Context, yml models.DeviceType, deviceType nb.DeviceType) {
	// Build map of desired power ports from YAML configuration
	desiredModuleBays := make(map[string]models.ModuleBay)
	for _, moduleBay := range yml.ModuleBays {
		desiredModuleBays[moduleBay.Name] = moduleBay
	}

	// Build map of existing power port templates from Nautobot
	existingTemplates := s.moduleBayTemplateSvc.ListByDeviceType(ctx, deviceType.Id)
	existingMap := make(map[string]nb.ModuleBayTemplate)
	for _, template := range existingTemplates {
		existingMap[template.Name] = template
	}

	// Process each desired power port: create new or update existing
	for name, moduleBay := range desiredModuleBays {
		templateRequest := nb.ModuleBayTemplateRequest{
			Name:       moduleBay.Name,
			Label:      nb.PtrString(moduleBay.Label),
			DeviceType: helpers.BuildNullableBulkWritableCircuitRequestTenant(deviceType.Id),
		}

		if existingTemplate, exists := existingMap[name]; !exists {
			_, _ = s.moduleBayTemplateSvc.Create(ctx, templateRequest)
		} else if !helpers.CompareJSONFields(existingTemplate, templateRequest) {
			_, _ = s.moduleBayTemplateSvc.Update(ctx, existingTemplate.Id, templateRequest)
		} else {
			log.Info("moduleBay unchanged skipping update", "name", templateRequest.Name, "deviceTypeId", deviceType.Id, "deviceTypeName", deviceType.Display)
		}
	}

	obsoletes := lo.OmitByKeys(existingMap, lo.Keys(desiredModuleBays))
	for _, obsolete := range obsoletes {
		_ = s.moduleBayTemplateSvc.Destroy(ctx, obsolete.Id)
	}
}
