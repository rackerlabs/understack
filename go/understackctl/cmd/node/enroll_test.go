package node

import (
	"reflect"
	"testing"
)

func TestBuildEnrollArgoArgsRequiredOnly(t *testing.T) {
	cmd := newCmdEnrollServer()

	args, err := buildEnrollArgoArgs(cmd, "10.46.6.165", &enrollOptions{})
	if err != nil {
		t.Fatalf("buildEnrollArgoArgs returned error: %v", err)
	}

	expected := []string{
		"-n", enrollWorkflowNamespace,
		"submit",
		"--from", enrollWorkflowTemplate,
		"-p", "ip_address=10.46.6.165",
	}
	if !reflect.DeepEqual(args, expected) {
		t.Fatalf("unexpected args: got %#v want %#v", args, expected)
	}
}

func TestBuildEnrollArgoArgsOptionalFlags(t *testing.T) {
	cmd := newCmdEnrollServer()
	if err := cmd.Flags().Set("old-password", "secret"); err != nil {
		t.Fatalf("set old-password: %v", err)
	}
	if err := cmd.Flags().Set("firmware-update", "true"); err != nil {
		t.Fatalf("set firmware-update: %v", err)
	}
	if err := cmd.Flags().Set("raid-configure", "false"); err != nil {
		t.Fatalf("set raid-configure: %v", err)
	}
	if err := cmd.Flags().Set("external-cmdb-id", "cmdb-123"); err != nil {
		t.Fatalf("set external-cmdb-id: %v", err)
	}
	if err := cmd.Flags().Set("log", "true"); err != nil {
		t.Fatalf("set log: %v", err)
	}

	opts := &enrollOptions{
		OldPassword:    "secret",
		FirmwareUpdate: true,
		RaidConfigure:  false,
		ExternalCMDBID: "cmdb-123",
		Logs:           true,
	}

	args, err := buildEnrollArgoArgs(cmd, "10.46.6.165", opts)
	if err != nil {
		t.Fatalf("buildEnrollArgoArgs returned error: %v", err)
	}

	expected := []string{
		"-n", enrollWorkflowNamespace,
		"submit",
		"--from", enrollWorkflowTemplate,
		"-p", "ip_address=10.46.6.165",
		"--log",
		"-p", "old_password=secret",
		"-p", "firmware_update=true",
		"-p", "raid_configure=false",
		"-p", "external_cmdb_id=cmdb-123",
	}
	if !reflect.DeepEqual(args, expected) {
		t.Fatalf("unexpected args: got %#v want %#v", args, expected)
	}
}
