package sync

import (
	"context"
	"errors"
	"testing"

	"github.com/rackerlabs/understack/go/nautobotop/internal/nautobot/syncerr"
)

func TestSyncItems(t *testing.T) {
	ctx := context.Background()
	infra := errors.New("auth failed")

	t.Run("all success", func(t *testing.T) {
		var seen []int
		res, err := syncItems(ctx, []int{1, 2, 3}, func(_ context.Context, n int) error {
			seen = append(seen, n)
			return nil
		})
		if err != nil {
			t.Fatalf("unexpected infra error: %v", err)
		}
		if res.HasFailures() {
			t.Errorf("expected no failures, got %+v", res.DataFailures)
		}
		if len(seen) != 3 {
			t.Errorf("expected all 3 items processed, got %v", seen)
		}
	})

	t.Run("one data error continues", func(t *testing.T) {
		var seen []string
		items := []string{"ok1", "bad", "ok2"}
		res, err := syncItems(ctx, items, func(_ context.Context, s string) error {
			seen = append(seen, s)
			if s == "bad" {
				return syncerr.NewDataError(s, errors.New("400 Bad Request"))
			}
			return nil
		})
		if err != nil {
			t.Fatalf("data error must not abort: %v", err)
		}
		if len(seen) != 3 {
			t.Errorf("expected to continue past the bad item, processed %v", seen)
		}
		if len(res.DataFailures) != 1 || res.DataFailures[0].Item != "bad" {
			t.Errorf("expected one recorded failure for 'bad', got %+v", res.DataFailures)
		}
	})

	t.Run("infra error stops", func(t *testing.T) {
		var seen []string
		items := []string{"ok1", "boom", "never"}
		res, err := syncItems(ctx, items, func(_ context.Context, s string) error {
			seen = append(seen, s)
			if s == "boom" {
				return infra
			}
			return nil
		})
		if !errors.Is(err, infra) {
			t.Fatalf("expected infra error to be returned, got %v", err)
		}
		if len(seen) != 2 {
			t.Errorf("expected to stop at the infra error, processed %v", seen)
		}
		if res.HasFailures() {
			t.Errorf("infra abort should not record data failures, got %+v", res.DataFailures)
		}
	})

	t.Run("mixed: data errors before an infra error", func(t *testing.T) {
		items := []string{"bad1", "bad2", "boom", "never"}
		res, err := syncItems(ctx, items, func(_ context.Context, s string) error {
			switch s {
			case "boom":
				return infra
			case "never":
				t.Fatal("should not reach item after infra error")
			default:
				return syncerr.NewDataError(s, errors.New("bad input"))
			}
			return nil
		})
		if !errors.Is(err, infra) {
			t.Fatalf("expected infra error, got %v", err)
		}
		// Data failures collected before the infra abort are preserved.
		if len(res.DataFailures) != 2 {
			t.Errorf("expected 2 data failures recorded before abort, got %+v", res.DataFailures)
		}
	})
}
