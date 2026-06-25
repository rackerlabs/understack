package controller

import (
	"fmt"
	"sort"
)

// ResourceNode defines a sync resource with explicit dependency declarations.
// The topological sort uses DependsOn to determine execution order automatically.
type ResourceNode struct {
	Name      string
	DependsOn []string
}

// topologicalSort using Kahn's algorithm here
// a deterministic execution order that respects all declared dependencies.
//
// Returns an error if:
//   - A cycle is detected (not a DAG)
//   - A node references a dependency that doesn't exist in the input
//   - Duplicate node names are provided
func topologicalSort(nodes []ResourceNode) ([]string, error) {
	if len(nodes) == 0 {
		return nil, nil
	}
	nodeSet := make(map[string]struct{}, len(nodes))
	for _, node := range nodes {
		if _, exists := nodeSet[node.Name]; exists {
			return nil, fmt.Errorf("duplicate node name: %q", node.Name)
		}
		nodeSet[node.Name] = struct{}{}
	}

	for _, node := range nodes {
		for _, dep := range node.DependsOn {
			if _, exists := nodeSet[dep]; !exists {
				return nil, fmt.Errorf("node %q depends on %q which does not exist", node.Name, dep)
			}
		}
	}

	inDegree := make(map[string]int, len(nodes))
	dependents := make(map[string][]string, len(nodes))

	for _, node := range nodes {
		inDegree[node.Name] = len(node.DependsOn)
		for _, dep := range node.DependsOn {
			dependents[dep] = append(dependents[dep], node.Name)
		}
	}

	var queue []string
	for _, node := range nodes {
		if inDegree[node.Name] == 0 {
			queue = append(queue, node.Name)
		}
	}
	sort.Strings(queue)

	result := make([]string, 0, len(nodes))

	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		result = append(result, current)

		children := dependents[current]
		sort.Strings(children)
		for _, child := range children {
			inDegree[child]--
			if inDegree[child] == 0 {
				queue = append(queue, child)
			}
		}
		sort.Strings(queue)
	}

	if len(result) != len(nodes) {
		var cycleNodes []string
		for name, degree := range inDegree {
			if degree > 0 {
				cycleNodes = append(cycleNodes, name)
			}
		}
		sort.Strings(cycleNodes)
		return nil, fmt.Errorf("dependency cycle detected involving nodes: %v", cycleNodes)
	}

	return result, nil
}
