package nautobot

import (
	"context"

	"go.yaml.in/yaml/v3"

	"github.com/charmbracelet/log"
	"github.com/samber/lo"

	nb "github.com/nautobot/go-nautobot/v2"
)

type DeviceTypes struct {
	DeviceTypes []DeviceType
}
type DeviceType struct {
	Manufacturer  string          `yaml:"manufacturer"`
	PartNumber    string          `yaml:"part_number"`
	Model         string          `yaml:"model"`
	UHeight       int             `yaml:"u_height"`
	IsFullDepth   bool            `yaml:"is_full_depth"`
	Comments      string          `yaml:"comments"`
	ConsolePorts  []ConsolePort   `yaml:"console-ports"`
	PowerPorts    []PowerPort     `yaml:"power-ports"`
	Interfaces    []Interface     `yaml:"interfaces"`
	ModuleBays    []ModuleBay     `yaml:"module-bays"`
	Class         string          `yaml:"class"`
	ResourceClass []ResourceClass `yaml:"resource_class"`
}

type ConsolePort struct {
	Name string `yaml:"name"`
	Type string `yaml:"type"`
}

type PowerPort struct {
	Name          string `yaml:"name"`
	Type          string `yaml:"type"`
	MaximumDraw   int    `yaml:"maximum_draw"`
	AllocatedDraw int    `yaml:"allocated_draw"`
}

type Interface struct {
	Name     string `yaml:"name"`
	Type     string `yaml:"type"`
	MgmtOnly bool   `yaml:"mgmt_only"`
}

type ModuleBay struct {
	Name     string `yaml:"name"`
	Position string `yaml:"position"`
	Label    string `yaml:"label,omitempty"`
}

type ResourceClass struct {
	Name     string `yaml:"name"`
	CPU      CPU    `yaml:"cpu"`
	Memory   Memory `yaml:"memory"`
	Drives   []Disk `yaml:"drives"`
	NicCount int    `yaml:"nic_count"`
}

type CPU struct {
	Cores int    `yaml:"cores"`
	Model string `yaml:"model"`
}

type Memory struct {
	Size int `yaml:"size"`
}

type Disk struct {
	Size int `yaml:"size"`
}

func (n *NautobotClient) SyncAllDeviceTypes(ctx context.Context, data map[string]string) error {
	var deviceTypes DeviceTypes
	for _, f := range data {
		var yml DeviceType

		if err := yaml.Unmarshal([]byte(f), &yml); err != nil {
			n.AddReport("yamlFailed", err.Error())
			return err
		}
		deviceTypes.DeviceTypes = append(deviceTypes.DeviceTypes, yml)

		manufacturer := n.GetManufacturerByName(context.Background(), yml.Manufacturer)
		if manufacturer.Id == "" {
			cm, _ := n.CreateNewManufacturer(context.Background(), nb.ManufacturerRequest{
				Name:        yml.Manufacturer,
				Description: nb.PtrString(yml.Manufacturer),
			})
			manufacturer = *cm
		}

		deviceType := n.GetDeviceTypeByName(context.Background(), yml.Model)
		if deviceType.Id == "" {
			dt, _ := n.CreateNewDeviceType(context.Background(), nb.WritableDeviceTypeRequest{
				Model:        yml.Model,
				PartNumber:   nb.PtrString(yml.PartNumber),
				UHeight:      nb.PtrInt32(int32(yml.UHeight)),
				IsFullDepth:  nb.PtrBool(yml.IsFullDepth),
				Comments:     nb.PtrString(yml.Comments),
				Manufacturer: *buildBulkWritableCableRequestStatus(manufacturer.Id),
			})
			deviceType = *dt
		}

		n.syncDeviceTypeInterfaceTemplate(ctx, yml, deviceType)
		n.syncDeviceTypeConsolePortTemplate(ctx, yml, deviceType)
		n.syncDeviceTypePowerPortTemplate(ctx, yml, deviceType)
		n.syncDeviceTypeModuleBayTemplate(ctx, yml, deviceType)
	}

	desiredDeviceTypes := make(map[string]DeviceType)
	for _, deviceType := range deviceTypes.DeviceTypes {
		desiredDeviceTypes[deviceType.Model] = deviceType
	}
	existingDeviceTypes := n.ListAllDeviceTypes(ctx)
	existingMap := make(map[string]nb.DeviceType, len(existingDeviceTypes))
	for _, template := range existingDeviceTypes {
		existingMap[template.Model] = template
	}
	obsoleteDeviceTypes := lo.OmitByKeys(existingMap, lo.Keys(desiredDeviceTypes))
	for _, obsoleteDeviceType := range obsoleteDeviceTypes {
		_ = n.DestroyDeviceType(ctx, obsoleteDeviceType.Id)
	}

	log.Info("SyncAllDevice Completed")
	return nil
}

func (n *NautobotClient) syncDeviceTypePowerPortTemplate(ctx context.Context, yml DeviceType, deviceType nb.DeviceType) {
	// Build map of desired power ports from YAML configuration
	desiredPorts := make(map[string]PowerPort)
	for _, port := range yml.PowerPorts {
		desiredPorts[port.Name] = port
	}

	// Build map of existing power port templates from Nautobot
	existingTemplates := n.ListAllPowerPortTemplate(ctx, deviceType.Id)
	existingMap := make(map[string]nb.PowerPortTemplate)
	for _, template := range existingTemplates {
		existingMap[template.Name] = template
	}

	// Process each desired power port: create new or update existing
	for portName, desiredPort := range desiredPorts {
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
			DeviceType:    buildNullableBulkWritableCircuitRequestTenant(deviceType.Id),
		}

		if existingTemplate, exists := existingMap[portName]; exists {
			_, _ = n.UpdatePowerPortTemplate(ctx, existingTemplate.Id, templateRequest)
		} else {
			_, _ = n.CreateNewPowerPortTemplate(ctx, templateRequest)
		}
	}

	obsoleteTemplates := lo.OmitByKeys(existingMap, lo.Keys(desiredPorts))
	for _, obsoleteTemplate := range obsoleteTemplates {
		_ = n.DestroyPowerPortTemplate(ctx, obsoleteTemplate.Id)
	}
}

func (n *NautobotClient) syncDeviceTypeConsolePortTemplate(ctx context.Context, yml DeviceType, deviceType nb.DeviceType) {
	// Build map of desired console ports from YAML configuration
	desiredPorts := make(map[string]ConsolePort)
	for _, port := range yml.ConsolePorts {
		desiredPorts[port.Name] = port
	}

	existingTemplates := n.ListAllConsolePortTemplateByDeviceType(ctx, deviceType.Id)
	existingMap := make(map[string]nb.ConsolePortTemplate)
	for _, template := range existingTemplates {
		existingMap[template.Name] = template
	}

	for portName, desiredPort := range desiredPorts {
		consolePortTypeChoice, _ := nb.NewConsolePortTypeChoicesFromValue(desiredPort.Type)
		templateRequest := nb.WritableConsolePortTemplateRequest{
			Name: portName,
			Type: &nb.PatchedWritableConsolePortTemplateRequestType{
				ConsolePortTypeChoices: consolePortTypeChoice,
			},
			DeviceType: buildNullableBulkWritableCircuitRequestTenant(deviceType.Id),
		}
		if existingTemplate, exists := existingMap[portName]; exists {
			_, _ = n.UpdateConsolePortTemplate(ctx, existingTemplate.Id, templateRequest)
		} else {
			_, _ = n.CreateNewConsolePortTemplate(ctx, templateRequest)
		}
	}
	obsoleteTemplates := lo.OmitByKeys(existingMap, lo.Keys(desiredPorts))
	for _, obsoleteTemplate := range obsoleteTemplates {
		_ = n.DestroyConsolePortTemplate(ctx, obsoleteTemplate.Id)
	}
}

func (n *NautobotClient) syncDeviceTypeInterfaceTemplate(ctx context.Context, yml DeviceType, deviceType nb.DeviceType) {
	// Build map of desired console ports from YAML configuration
	desiredInterfaceTemplate := make(map[string]Interface)
	for _, interfaceTmpl := range yml.Interfaces {
		desiredInterfaceTemplate[interfaceTmpl.Name] = interfaceTmpl
	}

	existingTemplates := n.ListAllInterfaceTemplateByDeviceType(ctx, deviceType.Id)
	existingMap := make(map[string]nb.InterfaceTemplate)
	for _, template := range existingTemplates {
		existingMap[template.Display] = template
	}
	for portName, interfaceTmpl := range desiredInterfaceTemplate {
		interfaceTemplateChoice, _ := nb.NewInterfaceTypeChoicesFromValue(interfaceTmpl.Type)

		templateRequest := nb.WritableInterfaceTemplateRequest{
			Name:       portName,
			Type:       *interfaceTemplateChoice,
			MgmtOnly:   nb.PtrBool(interfaceTmpl.MgmtOnly),
			DeviceType: buildNullableBulkWritableCircuitRequestTenant(deviceType.Id),
		}
		if existingTemplate, exists := existingMap[portName]; exists {
			_, _ = n.UpdateInterfaceTemplate(ctx, existingTemplate.Id, templateRequest)
		} else {
			_, _ = n.CreateNewInterfaceTemplate(ctx, templateRequest)
		}
	}
	obsoleteTemplates := lo.OmitByKeys(existingMap, lo.Keys(desiredInterfaceTemplate))
	for _, obsoleteTemplate := range obsoleteTemplates {
		_ = n.DestroyInterfaceTemplate(ctx, obsoleteTemplate.Id)
	}
}

func (n *NautobotClient) syncDeviceTypeModuleBayTemplate(ctx context.Context, yml DeviceType, deviceType nb.DeviceType) {
	// Build map of desired power ports from YAML configuration
	desiredModuleBays := make(map[string]ModuleBay)
	for _, moduleBay := range yml.ModuleBays {
		desiredModuleBays[moduleBay.Name] = moduleBay
	}

	// Build map of existing power port templates from Nautobot
	existingTemplates := n.ListAllModuleBayTemplateByDeviceType(ctx, deviceType.Id)
	existingMap := make(map[string]nb.ModuleBayTemplate)
	for _, template := range existingTemplates {
		existingMap[template.Name] = template
	}

	// Process each desired power port: create new or update existing
	for moduleBayName, moduleBay := range desiredModuleBays {
		templateRequest := nb.ModuleBayTemplateRequest{
			Name:       moduleBay.Name,
			Label:      nb.PtrString(moduleBay.Label),
			DeviceType: buildNullableBulkWritableCircuitRequestTenant(deviceType.Id),
		}

		if existingTemplate, exists := existingMap[moduleBayName]; exists {
			_, _ = n.UpdateModuleBayTemplate(ctx, existingTemplate.Id, templateRequest)
		} else {
			_, _ = n.CreateNewModuleBayTemplate(ctx, templateRequest)
		}
	}

	obsoleteTemplates := lo.OmitByKeys(existingMap, lo.Keys(desiredModuleBays))
	for _, obsoleteTemplate := range obsoleteTemplates {
		_ = n.DestroyModuleBayTemplate(ctx, obsoleteTemplate.Id)
	}
}

func (n *NautobotClient) CreateNewDeviceType(ctx context.Context, req nb.WritableDeviceTypeRequest) (*nb.DeviceType, error) {
	deviceType, resp, err := n.Client.DcimAPI.DcimDeviceTypesCreate(ctx).WritableDeviceTypeRequest(req).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("createNewDeviceType", "failed to create", "model", req.Model, "error", err.Error(), "response_body", bodyString)
		return nil, err
	}
	log.Printf("Created manufacture: %s", deviceType.Display)
	return deviceType, nil
}

func (n *NautobotClient) GetDeviceTypeByName(ctx context.Context, name string) nb.DeviceType {
	list, resp, err := n.Client.DcimAPI.DcimDeviceTypesList(ctx).Model([]string{name}).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("GetDeviceTypeByName", "failed to get", "name", name, "error", err.Error(), "response_body", bodyString)
		return nb.DeviceType{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return nb.DeviceType{}
	}
	return list.Results[0]
}

func (n *NautobotClient) ListAllDeviceTypes(ctx context.Context) []nb.DeviceType {
	list, resp, err := n.Client.DcimAPI.DcimDeviceTypesList(ctx).Depth(10).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("ListAllDeviceTypes", "failed to list", "error", err.Error(), "response_body", bodyString)
		return []nb.DeviceType{}
	}
	if list == nil || len(list.Results) == 0 || list.Results[0].Id == "" {
		return []nb.DeviceType{}
	}
	return list.Results
}

func (n *NautobotClient) DestroyDeviceType(ctx context.Context, id string) error {
	resp, err := n.Client.DcimAPI.DcimDeviceTypesDestroy(ctx, id).Execute()
	if err != nil {
		bodyString := readResponseBody(resp)
		n.AddReport("DestroyDeviceType", "failed to destroy", "id", id, "error", err.Error(), "response_body", bodyString)
		return err
	}
	return nil
}
