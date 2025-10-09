package deviceType

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/log"
	"github.com/gookit/goutil/envutil"
	"github.com/santhosh-tekuri/jsonschema/v5"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

func getDeviceTypesDir() string {
	deployPath := envutil.Getenv("UC_DEPLOY")
	if deployPath == "" {
		log.Fatal("UC_DEPLOY environment variable is not set")
	}
	return filepath.Join(deployPath, "hardware", "device-types")
}

func getKustomizationPath() string {
	deployPath := envutil.Getenv("UC_DEPLOY")
	if deployPath == "" {
		log.Fatal("UC_DEPLOY environment variable is not set")
	}
	return filepath.Join(deployPath, "hardware", "base", "kustomization.yaml")
}

func updateKustomization(fileName string, add bool) error {
	kustomizationPath := getKustomizationPath()

	// Read existing kustomization
	data, err := os.ReadFile(kustomizationPath)
	if err != nil {
		return fmt.Errorf("failed to read kustomization.yaml: %w", err)
	}

	var kustomization map[string]interface{}
	if err := yaml.Unmarshal(data, &kustomization); err != nil {
		return fmt.Errorf("failed to parse kustomization.yaml: %w", err)
	}

	// Navigate to configMapGenerator
	configMapGenerators, ok := kustomization["configMapGenerator"].([]interface{})
	if !ok {
		return fmt.Errorf("configMapGenerator not found or invalid format")
	}

	// Find the device-types configMap
	var deviceTypesMap map[string]interface{}
	for _, gen := range configMapGenerators {
		genMap := gen.(map[string]interface{})
		if genMap["name"] == "device-types" {
			deviceTypesMap = genMap
			break
		}
	}

	if deviceTypesMap == nil {
		return fmt.Errorf("device-types configMapGenerator not found")
	}

	// Get files array
	files, ok := deviceTypesMap["files"].([]interface{})
	if !ok {
		files = []interface{}{}
	}

	// Build the entry: filename=../device-types/filename
	entry := fmt.Sprintf("%s=../device-types/%s", fileName, fileName)

	if add {
		// Check if entry already exists
		for _, f := range files {
			if f.(string) == entry {
				log.Info("Entry already exists in kustomization.yaml", "file", fileName)
				return nil
			}
		}
		// Add the entry
		files = append(files, entry)
		log.Info("Added to kustomization.yaml", "file", fileName)
	} else {
		// Remove the entry
		var newFiles []interface{}
		found := false
		for _, f := range files {
			if f.(string) != entry {
				newFiles = append(newFiles, f)
			} else {
				found = true
			}
		}
		if !found {
			log.Warn("Entry not found in kustomization.yaml", "file", fileName)
		} else {
			log.Info("Removed from kustomization.yaml", "file", fileName)
		}
		files = newFiles
	}

	// Update the files array
	deviceTypesMap["files"] = files

	// Marshal back to YAML
	output, err := yaml.Marshal(kustomization)
	if err != nil {
		return fmt.Errorf("failed to marshal kustomization.yaml: %w", err)
	}

	// Write back
	if err := os.WriteFile(kustomizationPath, output, 0644); err != nil {
		return fmt.Errorf("failed to write kustomization.yaml: %w", err)
	}

	return nil
}

func NewCmdDeviceType() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "device-type",
		Short: "Manage device type definitions",
		Long:  "Create, delete, list, and show hardware device type definitions",
	}

	cmd.AddCommand(newCmdAdd())
	cmd.AddCommand(newCmdValidate())
	cmd.AddCommand(newCmdDelete())
	cmd.AddCommand(newCmdList())
	cmd.AddCommand(newCmdShow())

	return cmd
}

func newCmdAdd() *cobra.Command {
	return &cobra.Command{
		Use:   "add <file>",
		Short: "Add a device-type definition to the deployment",
		Long:  "Validate and add a device-type definition from a YAML file to the deployment repository",
		Args:  cobra.ExactArgs(1),
		RunE:  runAdd,
	}
}

func newCmdValidate() *cobra.Command {
	return &cobra.Command{
		Use:   "validate <file>",
		Short: "Validate a device-type definition",
		Long:  "Validate a device-type definition against the JSON schema without adding it to the deployment",
		Args:  cobra.ExactArgs(1),
		RunE:  runValidate,
	}
}

func newCmdDelete() *cobra.Command {
	return &cobra.Command{
		Use:   "delete <name>",
		Short: "Delete a device-type definition",
		Long:  "Delete a device-type definition by name",
		Args:  cobra.ExactArgs(1),
		RunE:  runDelete,
	}
}

func newCmdList() *cobra.Command {
	return &cobra.Command{
		Use:   "list",
		Short: "List all device-type definitions",
		Long:  "List all device-type definitions in the hardware/device-types directory",
		Args:  cobra.NoArgs,
		RunE:  runList,
	}
}

func newCmdShow() *cobra.Command {
	return &cobra.Command{
		Use:   "show <name>",
		Short: "Show details of a device-type",
		Long:  "Show detailed information about a specific device-type definition",
		Args:  cobra.ExactArgs(1),
		RunE:  runShow,
	}
}

func parseDeviceType(data []byte) (*DeviceType, error) {
	var deviceType DeviceType
	if err := yaml.Unmarshal(data, &deviceType); err != nil {
		return nil, fmt.Errorf("failed to parse YAML: %w", err)
	}
	return &deviceType, nil
}

func validateDeviceType(data []byte) (*DeviceType, error) {
	// Parse YAML into struct
	deviceType, err := parseDeviceType(data)
	if err != nil {
		return nil, err
	}

	// Get the schema file path
	deployPath := envutil.Getenv("UC_DEPLOY")
	var schemaPath string

	// Try to find schema - check both UC_DEPLOY and current working directory context
	possiblePaths := []string{
		filepath.Join(deployPath, "..", "..", "schema", "device-type.schema.json"),
		"../../schema/device-type.schema.json",
		"../../../schema/device-type.schema.json",
	}

	for _, path := range possiblePaths {
		if _, err := os.Stat(path); err == nil {
			schemaPath = path
			break
		}
	}

	if schemaPath == "" {
		return nil, fmt.Errorf("could not find device-type.schema.json in expected locations")
	}

	// Load and compile schema
	compiler := jsonschema.NewCompiler()
	if err := compiler.AddResource("schema.json", strings.NewReader(readSchemaFile(schemaPath))); err != nil {
		return nil, fmt.Errorf("failed to add schema resource: %w", err)
	}

	schema, err := compiler.Compile("schema.json")
	if err != nil {
		return nil, fmt.Errorf("failed to compile schema: %w", err)
	}

	// Convert to JSON for validation (jsonschema library works with JSON)
	jsonData, err := json.Marshal(deviceType)
	if err != nil {
		return nil, fmt.Errorf("failed to convert to JSON: %w", err)
	}

	var jsonDoc interface{}
	if err := json.Unmarshal(jsonData, &jsonDoc); err != nil {
		return nil, fmt.Errorf("failed to parse JSON: %w", err)
	}

	// Validate against schema
	if err := schema.Validate(jsonDoc); err != nil {
		return nil, fmt.Errorf("validation failed: %w", err)
	}

	return deviceType, nil
}

func readSchemaFile(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		log.Fatalf("Failed to read schema file: %v", err)
	}
	return string(data)
}

func generateFileName(manufacturer, model string) string {
	manufacturerClean := strings.ToLower(strings.ReplaceAll(manufacturer, " ", "-"))
	modelClean := strings.ToLower(strings.ReplaceAll(model, " ", "-"))
	return fmt.Sprintf("%s-%s.yaml", manufacturerClean, modelClean)
}

func runAdd(cmd *cobra.Command, args []string) error {
	sourceFile := args[0]

	// Read the file
	data, err := os.ReadFile(sourceFile)
	if err != nil {
		return fmt.Errorf("failed to read file: %w", err)
	}

	// Validate against JSON schema
	deviceType, err := validateDeviceType(data)
	if err != nil {
		return err
	}

	// Validate manufacturer and model are non-empty
	if deviceType.Manufacturer == "" || deviceType.Model == "" {
		return fmt.Errorf("manufacturer and model must be non-empty strings")
	}

	// Generate filename
	fileName := generateFileName(deviceType.Manufacturer, deviceType.Model)
	destPath := filepath.Join(getDeviceTypesDir(), fileName)

	// Check if file already exists
	if _, err := os.Stat(destPath); err == nil {
		return fmt.Errorf("device-type already exists at %s", destPath)
	}

	// Ensure the directory exists
	if err := os.MkdirAll(filepath.Dir(destPath), 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	// Copy the file to the destination
	if err := os.WriteFile(destPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write device-type file: %w", err)
	}

	log.Info("Device type added successfully", "path", destPath)

	// Update kustomization.yaml
	if err := updateKustomization(fileName, true); err != nil {
		return fmt.Errorf("failed to update kustomization.yaml: %w", err)
	}

	return nil
}

func runValidate(cmd *cobra.Command, args []string) error {
	sourceFile := args[0]

	// Read the file
	data, err := os.ReadFile(sourceFile)
	if err != nil {
		return fmt.Errorf("failed to read file: %w", err)
	}

	// Validate against JSON schema
	deviceType, err := validateDeviceType(data)
	if err != nil {
		return err
	}

	log.Info("Device type definition is valid",
		"class", deviceType.Class,
		"manufacturer", deviceType.Manufacturer,
		"model", deviceType.Model)

	return nil
}

func runDelete(cmd *cobra.Command, args []string) error {
	name := args[0]
	fileName := fmt.Sprintf("%s.yaml", name)
	filePath := filepath.Join(getDeviceTypesDir(), fileName)

	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		return fmt.Errorf("device-type %s not found", name)
	}

	if err := os.Remove(filePath); err != nil {
		return fmt.Errorf("failed to delete device-type: %w", err)
	}

	log.Info("Device type deleted", "name", name)

	// Update kustomization.yaml
	if err := updateKustomization(fileName, false); err != nil {
		return fmt.Errorf("failed to update kustomization.yaml: %w", err)
	}

	return nil
}

func runList(cmd *cobra.Command, args []string) error {
	deviceTypesDir := getDeviceTypesDir()
	entries, err := os.ReadDir(deviceTypesDir)
	if err != nil {
		if os.IsNotExist(err) {
			log.Info("No device types found - directory does not exist")
			return nil
		}
		return fmt.Errorf("failed to read device-types directory: %w", err)
	}

	if len(entries) == 0 {
		log.Info("No device types found")
		return nil
	}

	fmt.Println("Device Types:")
	for _, entry := range entries {
		if !entry.IsDir() && filepath.Ext(entry.Name()) == ".yaml" {
			name := entry.Name()[:len(entry.Name())-5] // Remove .yaml extension
			fmt.Printf("  - %s\n", name)
		}
	}

	return nil
}

func runShow(cmd *cobra.Command, args []string) error {
	name := args[0]
	fileName := fmt.Sprintf("%s.yaml", name)
	filePath := filepath.Join(getDeviceTypesDir(), fileName)

	data, err := os.ReadFile(filePath)
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("device-type %s not found", name)
		}
		return fmt.Errorf("failed to read device-type file: %w", err)
	}

	deviceType, err := parseDeviceType(data)
	if err != nil {
		return fmt.Errorf("failed to parse device-type: %w", err)
	}

	// Display device type information in a formatted way
	fmt.Printf("Device Type: %s\n", name)
	fmt.Printf("═══════════════════════════════════════════\n\n")

	// Basic information
	fmt.Printf("Class:         %s\n", deviceType.Class)
	fmt.Printf("Manufacturer:  %s\n", deviceType.Manufacturer)
	fmt.Printf("Model:         %s\n", deviceType.Model)
	fmt.Printf("Height (in u): %.0f\n", deviceType.UHeight)
	fmt.Printf("Full Depth:    %t\n\n", deviceType.IsFullDepth)

	// Interfaces
	if len(deviceType.Interfaces) > 0 {
		fmt.Printf("Interfaces:\n")
		for i, iface := range deviceType.Interfaces {
			fmt.Printf("  %d. %s (%s)", i+1, iface.Name, iface.Type)
			if iface.MgmtOnly {
				fmt.Printf(" [Management Only]")
			}
			fmt.Println()
		}
		fmt.Println()
	}

	// Resource Classes
	if len(deviceType.ResourceClass) > 0 {
		fmt.Printf("Resource Classes:\n")
		for i, rc := range deviceType.ResourceClass {
			fmt.Printf("\n  %d. %s\n", i+1, rc.Name)
			fmt.Printf("     ───────────────────────────────────\n")
			fmt.Printf("     CPU:    %d cores (%s)\n", rc.CPU.Cores, rc.CPU.Model)
			fmt.Printf("     Memory: %d GB\n", rc.Memory.Size)
			fmt.Printf("     NICs:   %d\n", rc.NICCount)

			if len(rc.Drives) > 0 {
				fmt.Printf("     Drives: ")
				for j, drive := range rc.Drives {
					if j > 0 {
						fmt.Printf(", ")
					}
					fmt.Printf("%d GB", drive.Size)
				}
				fmt.Println()
			}
		}
		fmt.Println()
	}

	return nil
}
