package syncerr

import (
	"errors"
	"net/http"
	"testing"
)

func TestClassify(t *testing.T) {
	baseErr := errors.New("boom")

	tests := []struct {
		name       string
		err        error
		statusCode int // 0 means no *http.Response is passed
		wantData   bool
		wantNil    bool
	}{
		{name: "nil error returns nil", err: nil, statusCode: http.StatusBadRequest, wantNil: true},

		// Data errors: request reached Nautobot and was rejected on input.
		{name: "400 is data", err: baseErr, statusCode: http.StatusBadRequest, wantData: true},
		{name: "404 is data", err: baseErr, statusCode: http.StatusNotFound, wantData: true},
		{name: "409 is data", err: baseErr, statusCode: http.StatusConflict, wantData: true},
		{name: "422 is data", err: baseErr, statusCode: http.StatusUnprocessableEntity, wantData: true},

		// Infrastructure errors: operator cannot make progress, should back off.
		{name: "401 is infra", err: baseErr, statusCode: http.StatusUnauthorized, wantData: false},
		{name: "403 is infra", err: baseErr, statusCode: http.StatusForbidden, wantData: false},
		{name: "500 is infra", err: baseErr, statusCode: http.StatusInternalServerError, wantData: false},
		{name: "502 is infra", err: baseErr, statusCode: http.StatusBadGateway, wantData: false},
		{name: "503 is infra", err: baseErr, statusCode: http.StatusServiceUnavailable, wantData: false},

		// No response at all (e.g. transport error / timeout) is infra.
		{name: "nil response is infra", err: baseErr, statusCode: 0, wantData: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var resp *http.Response
			if tt.statusCode != 0 {
				resp = &http.Response{StatusCode: tt.statusCode}
			}

			got := Classify("item-x", tt.err, resp)

			if tt.wantNil {
				if got != nil {
					t.Fatalf("Classify() = %v, want nil", got)
				}
				return
			}

			if got == nil {
				t.Fatal("Classify() = nil, want non-nil")
			}
			if IsDataError(got) != tt.wantData {
				t.Errorf("IsDataError(Classify()) = %v, want %v", IsDataError(got), tt.wantData)
			}
			// The original error must always remain unwrappable.
			if !errors.Is(got, tt.err) {
				t.Errorf("Classify() result does not wrap the original error")
			}
		})
	}
}

func TestDataErrorMessageAndUnwrap(t *testing.T) {
	base := errors.New("400 Bad Request")

	withItem := NewDataError("n11-21-network", base)
	if withItem.Error() != "n11-21-network: 400 Bad Request" {
		t.Errorf("unexpected message: %q", withItem.Error())
	}
	if !errors.Is(withItem, base) {
		t.Error("DataError should unwrap to the base error")
	}

	withoutItem := NewDataError("", base)
	if withoutItem.Error() != "400 Bad Request" {
		t.Errorf("unexpected message without item: %q", withoutItem.Error())
	}
}

func TestIsDataError(t *testing.T) {
	if IsDataError(nil) {
		t.Error("IsDataError(nil) should be false")
	}
	if IsDataError(errors.New("plain")) {
		t.Error("plain error should not be a data error")
	}
	// Wrapped data error should still be detected.
	wrapped := errors.Join(errors.New("context"), NewDataError("x", errors.New("y")))
	if !IsDataError(wrapped) {
		t.Error("wrapped DataError should be detected")
	}
}
