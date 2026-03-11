package deploy

import (
	"fmt"
	"strings"
)

const (
	deployTypeGlobal = "global"
	deployTypeSite   = "site"
	deployTypeAIO    = "aio"
)

func validateDeployType(deployType string, allowedTypes ...string) error {
	for _, allowed := range allowedTypes {
		if deployType == allowed {
			return nil
		}
	}

	return fmt.Errorf("invalid --type %q: must be %s", deployType, joinAllowedTypes(allowedTypes))
}

func joinAllowedTypes(allowedTypes []string) string {
	if len(allowedTypes) == 0 {
		return ""
	}
	if len(allowedTypes) == 1 {
		return allowedTypes[0]
	}

	return strings.Join(allowedTypes[:len(allowedTypes)-1], ", ") + ", or " + allowedTypes[len(allowedTypes)-1]
}
