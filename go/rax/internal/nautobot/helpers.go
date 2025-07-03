package nautobot

import nb "github.com/nautobot/go-nautobot/v2"

func buildBulkWritableCableRequestStatus(uuid string) *nb.BulkWritableCableRequestStatus {
	return &nb.BulkWritableCableRequestStatus{
		Id: &nb.BulkWritableCableRequestStatusId{
			String: nb.PtrString(uuid),
		},
	}
}

func buildNullableBulkWritableCircuitRequestTenant(uuid string) nb.NullableBulkWritableCircuitRequestTenant {
	return *nb.NewNullableBulkWritableCircuitRequestTenant(&nb.BulkWritableCircuitRequestTenant{
		Id: &nb.BulkWritableCableRequestStatusId{
			String: nb.PtrString(uuid),
		},
	})
}

func buildNullableBulkWritableRackRequestRackGroup(uuid string) *nb.NullableBulkWritableRackRequestRackGroup {
	return nb.NewNullableBulkWritableRackRequestRackGroup(&nb.BulkWritableRackRequestRackGroup{
		Id: &nb.BulkWritableCableRequestStatusId{
			String: nb.PtrString(uuid),
		},
	})
}
