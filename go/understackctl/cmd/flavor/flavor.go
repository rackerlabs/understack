package flavor

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

func getFlavorsDir() string {
	deployPath := envutil.Getenv("UC_DEPLOY")
	if deployPath == "" {
		log.Fatal("UC_DEPLOY environment variable is not set")
	}
	return filepath.Join(deployPath, "hardware", "flavors")
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

	// Find the flavors configMap
	var flavorsMap map[string]interface{}
	for _, gen := range configMapGenerators {
		genMap := gen.(map[string]interface{})
		if genMap["name"] == "flavors" {
			flavorsMap = genMap
			break
		}
	}

	if flavorsMap == nil {
		return fmt.Errorf("flavors configMapGenerator not found")
	}

	// Get files array
	files, ok := flavorsMap["files"].([]interface{})
	if !ok {
		files = []interface{}{}
	}

	// Build the entry: filename=../flavors/filename
	entry := fmt.Sprintf("%s=../flavors/%s", fileName, fileName)

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
	flavorsMap["files"] = files

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

func NewCmdFlavor() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "flavor",
		Short: "Manage hardware flavor definitions",
		Long:  "Create, delete, list, and show hardware flavor definitions for node matching",
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
		Short: "Add a flavor definition to the deployment",
		Long:  "Validate and add a flavor definition from a YAML file to the deployment repository",
		Args:  cobra.ExactArgs(1),
		RunE:  runAdd,
	}
}

func newCmdValidate() *cobra.Command {
	return &cobra.Command{
		Use:   "validate <file>",
		Short: "Validate a flavor definition",
		Long:  "Validate a flavor definition against the JSON schema without adding it to the deployment",
		Args:  cobra.ExactArgs(1),
		RunE:  runValidate,
	}
}

func newCmdDelete() *cobra.Command {
	return &cobra.Command{
		Use:   "delete <name>",
		Short: "Delete a flavor definition",
		Long:  "Delete a flavor definition by name",
		Args:  cobra.ExactArgs(1),
		RunE:  runDelete,
	}
}

func newCmdList() *cobra.Command {
	return &cobra.Command{
		Use:   "list",
		Short: "List all flavor definitions",
		Long:  "List all flavor definitions in the hardware/flavors directory",
		Args:  cobra.NoArgs,
		RunE:  runList,
	}
}

func newCmdShow() *cobra.Command {
	return &cobra.Command{
		Use:   "show <name>",
		Short: "Show details of a flavor",
		Long:  "Show detailed information about a specific flavor definition",
		Args:  cobra.ExactArgs(1),
		RunE:  runShow,
	}
}

func parseFlavor(data []byte) (*Flavor, error) {
	var flavor Flavor
	if err := yaml.Unmarshal(data, &flavor); err != nil {
		return nil, fmt.Errorf("failed to parse YAML: %w", err)
	}
	return &flavor, nil
}

func validateFlavor(data []byte) (*Flavor, error) {
	// Parse YAML into struct
	flavor, err := parseFlavor(data)
	if err != nil {
		return nil, err
	}

	// Get the schema file path
	deployPath := envutil.Getenv("UC_DEPLOY")
	var schemaPath string

	// Try to find schema - check both UC_DEPLOY and current working directory context
	possiblePaths := []string{
		filepath.Join(deployPath, "..", "..", "schema", "flavor.schema.json"),
		"../../schema/flavor.schema.json",
		"../../../schema/flavor.schema.json",
	}

	for _, path := range possiblePaths {
		if _, err := os.Stat(path); err == nil {
			schemaPath = path
			break
		}
	}

	if schemaPath == "" {
		return nil, fmt.Errorf("could not find flavor.schema.json in expected locations")
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
	jsonData, err := json.Marshal(flavor)
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

	return flavor, nil
}

func readSchemaFile(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		log.Fatalf("Failed to read schema file: %v", err)
	}
	return string(data)
}

func generateFileName(name string) string {
	return fmt.Sprintf("%s.yaml", name)
}

func runAdd(cmd *cobra.Command, args []string) error {
	sourceFile := args[0]

	// Read the file
	data, err := os.ReadFile(sourceFile)
	if err != nil {
		return fmt.Errorf("failed to read file: %w", err)
	}

	// Validate against JSON schema
	flavor, err := validateFlavor(data)
	if err != nil {
		return err
	}

	// Validate name is non-empty
	if flavor.Name == "" {
		return fmt.Errorf("name must be non-empty string")
	}

	// Generate filename
	fileName := generateFileName(flavor.Name)
	destPath := filepath.Join(getFlavorsDir(), fileName)

	// Check if file already exists
	if _, err := os.Stat(destPath); err == nil {
		return fmt.Errorf("flavor already exists at %s", destPath)
	}

	// Ensure the directory exists
	if err := os.MkdirAll(filepath.Dir(destPath), 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	// Copy the file to the destination
	if err := os.WriteFile(destPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write flavor file: %w", err)
	}

	log.Info("Flavor added successfully", "path", destPath)

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
	flavor, err := validateFlavor(data)
	if err != nil {
		return err
	}

	log.Info("Flavor definition is valid",
		"name", flavor.Name,
		"resource_class", flavor.ResourceClass)

	return nil
}

func runDelete(cmd *cobra.Command, args []string) error {
	name := args[0]
	fileName := generateFileName(name)
	filePath := filepath.Join(getFlavorsDir(), fileName)

	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		return fmt.Errorf("flavor %s not found", name)
	}

	if err := os.Remove(filePath); err != nil {
		return fmt.Errorf("failed to delete flavor: %w", err)
	}

	log.Info("Flavor deleted", "name", name)

	// Update kustomization.yaml
	if err := updateKustomization(fileName, false); err != nil {
		return fmt.Errorf("failed to update kustomization.yaml: %w", err)
	}

	return nil
}

func runList(cmd *cobra.Command, args []string) error {
	flavorsDir := getFlavorsDir()
	entries, err := os.ReadDir(flavorsDir)
	if err != nil {
		if os.IsNotExist(err) {
			log.Info("No flavors found - directory does not exist")
			return nil
		}
		return fmt.Errorf("failed to read flavors directory: %w", err)
	}

	if len(entries) == 0 {
		log.Info("No flavors found")
		return nil
	}

	fmt.Println("Flavors:")
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
	fileName := generateFileName(name)
	filePath := filepath.Join(getFlavorsDir(), fileName)

	data, err := os.ReadFile(filePath)
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("flavor %s not found", name)
		}
		return fmt.Errorf("failed to read flavor file: %w", err)
	}

	flavor, err := parseFlavor(data)
	if err != nil {
		return fmt.Errorf("failed to parse flavor: %w", err)
	}

	// Display flavor information in a formatted way
	fmt.Printf("Flavor: %s\n", name)
	fmt.Printf("═══════════════════════════════════════════\n\n")

	// Basic information
	fmt.Printf("Resource Class: %s\n", flavor.ResourceClass)
	fmt.Printf("  (Nova properties derived from device-type resource class)\n\n")

	// Traits
	if len(flavor.Traits) > 0 {
		fmt.Printf("Trait Requirements:\n")
		for i, trait := range flavor.Traits {
			fmt.Printf("  %d. %s [%s]\n", i+1, trait.Trait, trait.Requirement)
		}
		fmt.Println()
	} else {
		fmt.Printf("Trait Requirements: None (matches all nodes in resource class)\n\n")
	}

	return nil
}
