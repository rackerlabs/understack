package helpers

import (
	"encoding/json"
)

// CompareJSONFields compares two objects by marshaling them to JSON and checking if all fields
func CompareJSONFields(existing, desired any) bool {
	existingJSON, err := marshalToJSON(existing)
	if err != nil {
		return false
	}

	desiredJSON, err := marshalToJSON(desired)
	if err != nil {
		return false
	}

	var existingMap map[string]any
	if err := json.Unmarshal(existingJSON, &existingMap); err != nil {
		return false
	}

	var desiredMap map[string]any
	if err := json.Unmarshal(desiredJSON, &desiredMap); err != nil {
		return false
	}

	return compareJSONMaps(existingMap, desiredMap)
}

func marshalToJSON(obj any) ([]byte, error) {
	return json.Marshal(obj)
}

// compareJSONMaps recursively compares two JSON maps
// Returns true if all keys in desired exist in existing with matching values
func compareJSONMaps(existing, desired map[string]any) bool {
	for key, desiredValue := range desired {
		existingValue, exists := existing[key]
		if !exists {
			// Key doesn't exist in existing, consider it a mismatch
			return false
		}

		if !compareJSONValues(existingValue, desiredValue) {
			return false
		}
	}
	return true
}

// compareJSONValues compares two JSON values recursively
// Handles all JSON types: objects, arrays, strings, numbers, booleans, null
func compareJSONValues(existing, desired any) bool {
	// Handle nil values
	if desired == nil {
		return existing == nil
	}
	if existing == nil {
		return false
	}

	// If both are maps (nested objects), compare recursively
	existingMap, existingIsMap := existing.(map[string]any)
	desiredMap, desiredIsMap := desired.(map[string]any)

	if existingIsMap && desiredIsMap {
		// Both are nested objects - use recursive comparison
		// This handles: Manufacturer {id, name, ...} vs {id}
		return compareJSONMaps(existingMap, desiredMap)
	}

	// Special case: existing is a nested object, but desired is a primitive
	// This handles the Label/Value pattern (30+ types):
	// existing: {"label": "SFP+ (10GE)", "value": "10gbase-x-sfpp"}
	// desired: "10gbase-x-sfpp"
	// Also handles: {"id": "uuid", "name": "..."} vs "uuid"
	if existingIsMap && !desiredIsMap {
		return compareNestedObjectWithPrimitive(existingMap, desired)
	}

	// Special case: desired is a nested object, but existing is a primitive
	// This handles reverse case:
	// existing: "10gbase-x-sfpp"
	// desired: {"value": "10gbase-x-sfpp"}
	if !existingIsMap && desiredIsMap {
		return comparePrimitiveWithNestedObject(existing, desiredMap)
	}

	// If both are slices (arrays), compare recursively
	existingSlice, existingIsSlice := existing.([]any)
	desiredSlice, desiredIsSlice := desired.([]any)

	if existingIsSlice && desiredIsSlice {
		// Arrays must have same length
		if len(existingSlice) != len(desiredSlice) {
			return false
		}
		// Compare element by element
		for i := range desiredSlice {
			if !compareJSONValues(existingSlice[i], desiredSlice[i]) {
				return false
			}
		}
		return true
	}

	// Handle type mismatches (e.g., array vs primitive)
	if existingIsSlice != desiredIsSlice {
		return false
	}
	return comparePrimitiveValues(existing, desired)
}

// comparePrimitiveValues compares primitive JSON values (string, number, boolean)
// Handles number type normalization (JSON unmarshals all numbers as float64)
func comparePrimitiveValues(existing, desired any) bool {
	// Direct comparison works for most cases
	if existing == desired {
		return true
	}

	// Handle number comparison with type conversion
	// JSON unmarshals all numbers as float64, but they might be compared with int, etc.
	existingFloat, existingIsFloat := existing.(float64)
	desiredFloat, desiredIsFloat := desired.(float64)

	if existingIsFloat && desiredIsFloat {
		// Both are float64, direct comparison
		return existingFloat == desiredFloat
	}

	// If types don't match, they're not equal
	return false
}

// compareNestedObjectWithPrimitive compares a nested object (existing) with a primitive value (desired)
//
// This handles two major Nautobot API patterns:
//
// Pattern 1: Label/Value Types (30+ types)
//   - existing: {"label": "SFP+ (10GE)", "value": "10gbase-x-sfpp"}
//   - desired: "10gbase-x-sfpp"
//   - Applies to: InterfaceType, ConsolePortType, PowerPortType, CableType, InterfaceMode,
//     PowerFeedPhase, PowerFeedSupply, DeviceFace, RackType, PrefixType, etc.
//
// Pattern 2: ID Reference Types (20+ types)
//   - existing: {"id": "uuid", "name": "Cisco", "display": "Cisco", ...}
//   - desired: "uuid"
//   - Applies to: Manufacturer, DeviceType, Location, Status, Role, Tenant, Platform, etc.
//
// Strategy:
// 1. If nested object has "id" field, compare it with desired (ID reference pattern)
// 2. If nested object has "value" field, compare it with desired (Label/Value pattern)
// 3. Otherwise, return false (incompatible types)
//
// Note: "id" takes precedence over "value" if both exist
func compareNestedObjectWithPrimitive(existingMap map[string]any, desired any) bool {
	// Strategy 1: Check if nested object has "id" field (ID reference pattern)
	// This handles: {"id": "uuid", ...} vs "uuid"
	if id, hasID := existingMap["id"]; hasID {
		return comparePrimitiveValues(id, desired)
	}

	// Strategy 2: Check if nested object has "value" field (Label/Value pattern)
	// This handles: {"label": "...", "value": "..."} vs "..."
	if value, hasValue := existingMap["value"]; hasValue {
		return comparePrimitiveValues(value, desired)
	}

	// No "id" or "value" field - types are incompatible
	// This is expected to fail - nested object doesn't follow known patterns
	return false
}

// comparePrimitiveWithNestedObject compares a primitive value (existing) with a nested object (desired)
//
// This handles the reverse case where the request sends a nested object but API might return a primitive.
// This is less common but included for completeness.
//
// Strategy:
// 1. If nested object has "id" field, compare existing with it
// 2. If nested object has "value" field, compare existing with it
// 3. Otherwise, return false (incompatible types)
//
// Note: "id" takes precedence over "value" if both exist
func comparePrimitiveWithNestedObject(existing any, desiredMap map[string]any) bool {
	// Strategy 1: Check if nested object has "id" field
	if id, hasID := desiredMap["id"]; hasID {
		return comparePrimitiveValues(existing, id)
	}

	// Strategy 2: Check if nested object has "value" field
	if value, hasValue := desiredMap["value"]; hasValue {
		return comparePrimitiveValues(existing, value)
	}

	// No "id" or "value" field - types are incompatible
	return false
}
