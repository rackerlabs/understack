package sync

import nb "github.com/nautobot/go-nautobot/v3"

func optionalID(id string) *string {
	if id == "" {
		return nil
	}
	return nb.PtrString(id)
}
