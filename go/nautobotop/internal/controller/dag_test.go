package controller

import (
	"testing"
)

func TestTopologicalSort(t *testing.T) {
	tests := []struct {
		name      string
		nodes     []ResourceNode
		want      []string
		wantErr   bool
		errSubstr string
	}{
		{
			name:  "empty input returns nil",
			nodes: nil,
			want:  nil,
		},
		{
			name: "single node with no dependencies",
			nodes: []ResourceNode{
				{Name: "a"},
			},
			want: []string{"a"},
		},
		{
			name: "two independent nodes sorted alphabetically",
			nodes: []ResourceNode{
				{Name: "b"},
				{Name: "a"},
			},
			want: []string{"a", "b"},
		},
		{
			name: "linear chain a -> b -> c",
			nodes: []ResourceNode{
				{Name: "c", DependsOn: []string{"b"}},
				{Name: "a"},
				{Name: "b", DependsOn: []string{"a"}},
			},
			want: []string{"a", "b", "c"},
		},
		{
			name: "diamond dependency: d depends on b and c, both depend on a",
			nodes: []ResourceNode{
				{Name: "d", DependsOn: []string{"b", "c"}},
				{Name: "b", DependsOn: []string{"a"}},
				{Name: "c", DependsOn: []string{"a"}},
				{Name: "a"},
			},
			want: []string{"a", "b", "c", "d"},
		},
		{
			name: "multiple roots with shared dependency",
			nodes: []ResourceNode{
				{Name: "location", DependsOn: []string{"locationTypes"}},
				{Name: "locationTypes"},
				{Name: "role"},
				{Name: "rack", DependsOn: []string{"location"}},
				{Name: "device", DependsOn: []string{"location", "rack", "role"}},
			},
			want: []string{"locationTypes", "location", "rack", "role", "device"},
		},
		{
			name: "real-world resource ordering matches expected",
			nodes: []ResourceNode{
				{Name: "locationTypes"},
				{Name: "location", DependsOn: []string{"locationTypes"}},
				{Name: "rir"},
				{Name: "role"},
				{Name: "deviceType"},
				{Name: "rackGroup", DependsOn: []string{"location"}},
				{Name: "vlanGroup", DependsOn: []string{"location"}},
				{Name: "rack", DependsOn: []string{"location", "rackGroup"}},
				{Name: "tenantGroup"},
				{Name: "tenant", DependsOn: []string{"tenantGroup"}},
				{Name: "device", DependsOn: []string{"deviceType", "location", "rack", "role", "tenant"}},
				{Name: "clusterType"},
				{Name: "clusterGroup"},
				{Name: "cluster", DependsOn: []string{"clusterType", "clusterGroup", "location", "device"}},
				{Name: "namespace", DependsOn: []string{"location", "tenant"}},
				{Name: "vlan", DependsOn: []string{"vlanGroup", "location", "tenant", "role"}},
				{Name: "prefix", DependsOn: []string{"namespace", "rir", "location", "vlan", "tenant", "role"}},
			},
			want: []string{
				"clusterGroup", "clusterType", "deviceType", "locationTypes",
				"location",
				"rackGroup", "rir", "role", "tenantGroup", "vlanGroup",
				"rack", "tenant",
				"device", "namespace", "vlan",
				"cluster",
				"prefix",
			},
		},
		{
			name: "simple cycle between two nodes",
			nodes: []ResourceNode{
				{Name: "a", DependsOn: []string{"b"}},
				{Name: "b", DependsOn: []string{"a"}},
			},
			wantErr:   true,
			errSubstr: "dependency cycle detected",
		},
		{
			name: "three-node cycle",
			nodes: []ResourceNode{
				{Name: "a", DependsOn: []string{"c"}},
				{Name: "b", DependsOn: []string{"a"}},
				{Name: "c", DependsOn: []string{"b"}},
			},
			wantErr:   true,
			errSubstr: "dependency cycle detected",
		},
		{
			name: "self-referencing node",
			nodes: []ResourceNode{
				{Name: "a", DependsOn: []string{"a"}},
			},
			wantErr:   true,
			errSubstr: "dependency cycle detected",
		},
		{
			name: "dependency on non-existent node",
			nodes: []ResourceNode{
				{Name: "a", DependsOn: []string{"ghost"}},
			},
			wantErr:   true,
			errSubstr: "does not exist",
		},
		{
			name: "duplicate node names",
			nodes: []ResourceNode{
				{Name: "a"},
				{Name: "a"},
			},
			wantErr:   true,
			errSubstr: "duplicate node name",
		},
		{
			name: "complex graph with independent subtrees",
			nodes: []ResourceNode{
				{Name: "x1"},
				{Name: "x2", DependsOn: []string{"x1"}},
				{Name: "x3", DependsOn: []string{"x1"}},
				{Name: "y1"},
				{Name: "y2", DependsOn: []string{"y1"}},
				{Name: "z", DependsOn: []string{"x2", "y2"}},
			},
			want: []string{"x1", "x2", "x3", "y1", "y2", "z"},
		},
		{
			name: "wide fan-out from single root",
			nodes: []ResourceNode{
				{Name: "root"},
				{Name: "child1", DependsOn: []string{"root"}},
				{Name: "child2", DependsOn: []string{"root"}},
				{Name: "child3", DependsOn: []string{"root"}},
				{Name: "child4", DependsOn: []string{"root"}},
			},
			want: []string{"root", "child1", "child2", "child3", "child4"},
		},
		{
			name: "wide fan-in to single leaf",
			nodes: []ResourceNode{
				{Name: "a"},
				{Name: "b"},
				{Name: "c"},
				{Name: "leaf", DependsOn: []string{"a", "b", "c"}},
			},
			want: []string{"a", "b", "c", "leaf"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := topologicalSort(tt.nodes)

			if tt.wantErr {
				if err == nil {
					t.Fatalf("expected error containing %q, got nil", tt.errSubstr)
				}
				if tt.errSubstr != "" && !containsSubstring(err.Error(), tt.errSubstr) {
					t.Fatalf("expected error containing %q, got: %v", tt.errSubstr, err)
				}
				return
			}

			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			if tt.want == nil && got == nil {
				return
			}

			if len(got) != len(tt.want) {
				t.Fatalf("length mismatch: got %d, want %d\ngot:  %v\nwant: %v", len(got), len(tt.want), got, tt.want)
			}

			// Verify the order respects all dependencies (not just exact match)
			verifyDependencyOrder(t, tt.nodes, got)

			// Also verify exact expected output for determinism
			for i := range got {
				if got[i] != tt.want[i] {
					t.Errorf("position %d: got %q, want %q\nfull got:  %v\nfull want: %v", i, got[i], tt.want[i], got, tt.want)
					break
				}
			}
		})
	}
}

// verifyDependencyOrder checks that for every node, all its dependencies
// appear earlier in the result slice.
func verifyDependencyOrder(t *testing.T, nodes []ResourceNode, result []string) {
	t.Helper()

	position := make(map[string]int, len(result))
	for i, name := range result {
		position[name] = i
	}

	for _, node := range nodes {
		nodePos, exists := position[node.Name]
		if !exists {
			t.Errorf("node %q missing from result", node.Name)
			continue
		}
		for _, dep := range node.DependsOn {
			depPos, exists := position[dep]
			if !exists {
				t.Errorf("dependency %q of node %q missing from result", dep, node.Name)
				continue
			}
			if depPos >= nodePos {
				t.Errorf("dependency violation: %q (pos %d) must come before %q (pos %d)", dep, depPos, node.Name, nodePos)
			}
		}
	}
}

func containsSubstring(s, substr string) bool {
	return len(s) >= len(substr) && searchSubstring(s, substr)
}

func searchSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
