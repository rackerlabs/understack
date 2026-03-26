package helpers

import (
	"testing"
)

func TestCompareJSONFields(t *testing.T) {
	tests := []struct {
		name     string
		existing any
		desired  any
		want     bool
	}{
		// === Basic primitives ===
		{
			name:     "identical strings",
			existing: map[string]any{"name": "foo"},
			desired:  map[string]any{"name": "foo"},
			want:     true,
		},
		{
			name:     "different strings",
			existing: map[string]any{"name": "foo"},
			desired:  map[string]any{"name": "bar"},
			want:     false,
		},
		{
			name:     "identical numbers",
			existing: map[string]any{"count": float64(42)},
			desired:  map[string]any{"count": float64(42)},
			want:     true,
		},
		{
			name:     "identical booleans",
			existing: map[string]any{"active": true},
			desired:  map[string]any{"active": true},
			want:     true,
		},
		{
			name:     "nil values both sides",
			existing: map[string]any{"val": nil},
			desired:  map[string]any{"val": nil},
			want:     true,
		},
		{
			name:     "nil desired vs non-nil existing",
			existing: map[string]any{"val": "something"},
			desired:  map[string]any{"val": nil},
			want:     false,
		},
		// === Desired is subset of existing (extra keys in existing are OK) ===
		{
			name:     "existing has extra keys",
			existing: map[string]any{"id": "1", "name": "foo", "extra": "bar"},
			desired:  map[string]any{"id": "1", "name": "foo"},
			want:     true,
		},
		{
			name:     "desired has key missing from existing",
			existing: map[string]any{"id": "1"},
			desired:  map[string]any{"id": "1", "name": "foo"},
			want:     false,
		},

		// === Array of strings - order independent ===
		{
			name:     "string array same order",
			existing: map[string]any{"tags": []any{"a", "b", "c"}},
			desired:  map[string]any{"tags": []any{"a", "b", "c"}},
			want:     true,
		},
		{
			name:     "string array different order",
			existing: map[string]any{"tags": []any{"c", "a", "b"}},
			desired:  map[string]any{"tags": []any{"a", "b", "c"}},
			want:     true,
		},
		{
			name:     "string array reversed",
			existing: map[string]any{"tags": []any{"z", "y", "x"}},
			desired:  map[string]any{"tags": []any{"x", "y", "z"}},
			want:     true,
		},
		{
			name:     "string array different lengths",
			existing: map[string]any{"tags": []any{"a", "b"}},
			desired:  map[string]any{"tags": []any{"a", "b", "c"}},
			want:     false,
		},
		{
			name:     "string array different values",
			existing: map[string]any{"tags": []any{"a", "b", "c"}},
			desired:  map[string]any{"tags": []any{"a", "b", "d"}},
			want:     false,
		},
		{
			name:     "empty arrays",
			existing: map[string]any{"tags": []any{}},
			desired:  map[string]any{"tags": []any{}},
			want:     true,
		},

		// === Array of numbers - order independent ===
		{
			name:     "number array same order",
			existing: map[string]any{"ids": []any{1.0, 2.0, 3.0}},
			desired:  map[string]any{"ids": []any{1.0, 2.0, 3.0}},
			want:     true,
		},
		{
			name:     "number array different order",
			existing: map[string]any{"ids": []any{3.0, 1.0, 2.0}},
			desired:  map[string]any{"ids": []any{1.0, 2.0, 3.0}},
			want:     true,
		},
		{
			name:     "number array different values",
			existing: map[string]any{"ids": []any{1.0, 2.0, 3.0}},
			desired:  map[string]any{"ids": []any{1.0, 2.0, 4.0}},
			want:     false,
		},

		// === Array of objects - order independent ===
		{
			name: "object array same order",
			existing: map[string]any{"items": []any{
				map[string]any{"id": "1", "name": "a"},
				map[string]any{"id": "2", "name": "b"},
			}},
			desired: map[string]any{"items": []any{
				map[string]any{"id": "1", "name": "a"},
				map[string]any{"id": "2", "name": "b"},
			}},
			want: true,
		},
		{
			name: "object array different order",
			existing: map[string]any{"items": []any{
				map[string]any{"id": "2", "name": "b"},
				map[string]any{"id": "1", "name": "a"},
			}},
			desired: map[string]any{"items": []any{
				map[string]any{"id": "1", "name": "a"},
				map[string]any{"id": "2", "name": "b"},
			}},
			want: true,
		},
		{
			name: "object array with extra keys in existing objects",
			existing: map[string]any{"items": []any{
				map[string]any{"id": "2", "name": "b", "extra": "x"},
				map[string]any{"id": "1", "name": "a", "extra": "y"},
			}},
			desired: map[string]any{"items": []any{
				map[string]any{"id": "1", "name": "a"},
				map[string]any{"id": "2", "name": "b"},
			}},
			want: true,
		},
		{
			name: "object array mismatch",
			existing: map[string]any{"items": []any{
				map[string]any{"id": "1", "name": "a"},
				map[string]any{"id": "2", "name": "WRONG"},
			}},
			desired: map[string]any{"items": []any{
				map[string]any{"id": "1", "name": "a"},
				map[string]any{"id": "2", "name": "b"},
			}},
			want: false,
		},

		// === Duplicate elements in arrays ===
		{
			name:     "duplicate strings same count",
			existing: map[string]any{"tags": []any{"a", "a", "b"}},
			desired:  map[string]any{"tags": []any{"b", "a", "a"}},
			want:     true,
		},
		{
			name:     "duplicate strings different count",
			existing: map[string]any{"tags": []any{"a", "a", "b"}},
			desired:  map[string]any{"tags": []any{"a", "b", "b"}},
			want:     false,
		},
		{
			name: "duplicate objects same count different order",
			existing: map[string]any{"items": []any{
				map[string]any{"id": "1"},
				map[string]any{"id": "1"},
				map[string]any{"id": "2"},
			}},
			desired: map[string]any{"items": []any{
				map[string]any{"id": "2"},
				map[string]any{"id": "1"},
				map[string]any{"id": "1"},
			}},
			want: true,
		},

		// === Nested arrays (array of arrays) - order independent ===
		{
			name: "nested arrays different order",
			existing: map[string]any{"matrix": []any{
				[]any{"b", "a"},
				[]any{"d", "c"},
			}},
			desired: map[string]any{"matrix": []any{
				[]any{"c", "d"},
				[]any{"a", "b"},
			}},
			want: true,
		},
		{
			name: "nested arrays mismatch",
			existing: map[string]any{"matrix": []any{
				[]any{"a", "b"},
				[]any{"c", "d"},
			}},
			desired: map[string]any{"matrix": []any{
				[]any{"a", "b"},
				[]any{"c", "e"},
			}},
			want: false,
		},

		// === Mixed type arrays ===
		{
			name:     "mixed types same order",
			existing: map[string]any{"data": []any{"hello", 42.0, true, nil}},
			desired:  map[string]any{"data": []any{"hello", 42.0, true, nil}},
			want:     true,
		},
		{
			name:     "mixed types different order",
			existing: map[string]any{"data": []any{true, nil, "hello", 42.0}},
			desired:  map[string]any{"data": []any{"hello", 42.0, true, nil}},
			want:     true,
		},

		// === Nautobot-specific: nested object vs primitive in arrays ===
		{
			name: "array of id-ref objects vs array of strings different order",
			existing: map[string]any{"roles": []any{
				map[string]any{"id": "uuid-3", "name": "admin"},
				map[string]any{"id": "uuid-1", "name": "viewer"},
				map[string]any{"id": "uuid-2", "name": "editor"},
			}},
			desired: map[string]any{"roles": []any{"uuid-1", "uuid-2", "uuid-3"}},
			want:    true,
		},
		{
			name: "array of label-value objects vs array of strings different order",
			existing: map[string]any{"types": []any{
				map[string]any{"label": "Type B", "value": "type-b"},
				map[string]any{"label": "Type A", "value": "type-a"},
			}},
			desired: map[string]any{"types": []any{"type-a", "type-b"}},
			want:    true,
		},
		{
			name: "array of id-ref objects vs strings mismatch",
			existing: map[string]any{"roles": []any{
				map[string]any{"id": "uuid-1"},
				map[string]any{"id": "uuid-2"},
			}},
			desired: map[string]any{"roles": []any{"uuid-1", "uuid-3"}},
			want:    false,
		},

		// === Deeply nested structures ===
		{
			name: "deeply nested objects with arrays in different order",
			existing: map[string]any{
				"config": map[string]any{
					"ports": []any{
						map[string]any{"id": "p2", "vlans": []any{"v2", "v1"}},
						map[string]any{"id": "p1", "vlans": []any{"v3", "v1"}},
					},
				},
			},
			desired: map[string]any{
				"config": map[string]any{
					"ports": []any{
						map[string]any{"id": "p1", "vlans": []any{"v1", "v3"}},
						map[string]any{"id": "p2", "vlans": []any{"v1", "v2"}},
					},
				},
			},
			want: true,
		},

		// === Edge cases ===
		{
			name:     "array vs primitive type mismatch",
			existing: map[string]any{"val": []any{"a"}},
			desired:  map[string]any{"val": "a"},
			want:     false,
		},
		{
			name:     "single element arrays different order is same",
			existing: map[string]any{"tags": []any{"only"}},
			desired:  map[string]any{"tags": []any{"only"}},
			want:     true,
		},
		{
			name:     "boolean arrays different order",
			existing: map[string]any{"flags": []any{false, true}},
			desired:  map[string]any{"flags": []any{true, false}},
			want:     true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := CompareJSONFields(tt.existing, tt.desired)
			if got != tt.want {
				t.Errorf("CompareJSONFields() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestCompareJSONFields_Structs(t *testing.T) {
	type Inner struct {
		ID   string `json:"id"`
		Name string `json:"name"`
	}
	type Outer struct {
		Title string   `json:"title"`
		Items []Inner  `json:"items"`
		Tags  []string `json:"tags"`
	}

	tests := []struct {
		name     string
		existing Outer
		desired  Outer
		want     bool
	}{
		{
			name: "struct with arrays in different order",
			existing: Outer{
				Title: "test",
				Items: []Inner{{ID: "2", Name: "b"}, {ID: "1", Name: "a"}},
				Tags:  []string{"z", "y", "x"},
			},
			desired: Outer{
				Title: "test",
				Items: []Inner{{ID: "1", Name: "a"}, {ID: "2", Name: "b"}},
				Tags:  []string{"x", "y", "z"},
			},
			want: true,
		},
		{
			name: "struct with different array values",
			existing: Outer{
				Title: "test",
				Items: []Inner{{ID: "1", Name: "a"}},
				Tags:  []string{"x"},
			},
			desired: Outer{
				Title: "test",
				Items: []Inner{{ID: "1", Name: "DIFFERENT"}},
				Tags:  []string{"x"},
			},
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := CompareJSONFields(tt.existing, tt.desired)
			if got != tt.want {
				t.Errorf("CompareJSONFields() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestCompareJSONSlices(t *testing.T) {
	tests := []struct {
		name     string
		existing []any
		desired  []any
		want     bool
	}{
		{
			name:     "both empty",
			existing: []any{},
			desired:  []any{},
			want:     true,
		},
		{
			name:     "both nil-like empty",
			existing: nil,
			desired:  nil,
			want:     true,
		},
		{
			name:     "single string match",
			existing: []any{"a"},
			desired:  []any{"a"},
			want:     true,
		},
		{
			name:     "strings shuffled",
			existing: []any{"c", "a", "b"},
			desired:  []any{"b", "c", "a"},
			want:     true,
		},
		{
			name:     "length mismatch",
			existing: []any{"a", "b"},
			desired:  []any{"a"},
			want:     false,
		},
		{
			name:     "value mismatch",
			existing: []any{"a", "b"},
			desired:  []any{"a", "c"},
			want:     false,
		},
		{
			name:     "duplicates matched correctly",
			existing: []any{"a", "a", "b"},
			desired:  []any{"a", "b", "a"},
			want:     true,
		},
		{
			name:     "duplicates count mismatch",
			existing: []any{"a", "a", "b"},
			desired:  []any{"a", "b", "b"},
			want:     false,
		},
		{
			name: "objects shuffled",
			existing: []any{
				map[string]any{"x": 2.0},
				map[string]any{"x": 1.0},
			},
			desired: []any{
				map[string]any{"x": 1.0},
				map[string]any{"x": 2.0},
			},
			want: true,
		},
		{
			name: "nested object with id vs primitive shuffled",
			existing: []any{
				map[string]any{"id": "b"},
				map[string]any{"id": "a"},
			},
			desired: []any{"a", "b"},
			want:    true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := compareJSONSlices(tt.existing, tt.desired)
			if got != tt.want {
				t.Errorf("compareJSONSlices() = %v, want %v", got, tt.want)
			}
		})
	}
}
