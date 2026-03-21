package node

import (
	"reflect"
	"testing"
)

func TestBuildInspectArgoArgs(t *testing.T) {
	args := buildInspectArgoArgs("node-123", &inspectOptions{})

	expected := []string{
		"-n", enrollWorkflowNamespace,
		"submit",
		"--from", inspectWorkflowTemplate,
		"-p", "node=node-123",
	}
	if !reflect.DeepEqual(args, expected) {
		t.Fatalf("unexpected args: got %#v want %#v", args, expected)
	}
}

func TestBuildInspectArgoArgsWithLogs(t *testing.T) {
	args := buildInspectArgoArgs("node-123", &inspectOptions{Logs: true})

	expected := []string{
		"-n", enrollWorkflowNamespace,
		"submit",
		"--from", inspectWorkflowTemplate,
		"-p", "node=node-123",
		"--log",
	}
	if !reflect.DeepEqual(args, expected) {
		t.Fatalf("unexpected args: got %#v want %#v", args, expected)
	}
}
