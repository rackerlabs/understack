package cache

import (
	"testing"
)

func TestCache(t *testing.T) {
	cache, err := New(0)
	if err != nil {
		t.Fatalf("failed to create cache: %v", err)
	}
	defer cache.Close()
	key := BuildKey("locations")
	value := "test-value"
	cache.Set(key, value)

	got, ok := cache.Get(key)
	if !ok {
		t.Fatal("expected value to be in cache")
	}
	if got != value {
		t.Errorf("expected %v, got %v", value, got)
	}
	_, ok = cache.Get("non-existent")
	if ok {
		t.Error("expected key to not be in cache")
	}
	cache.Delete(key)
	_, ok = cache.Get(key)
	if ok {
		t.Error("expected key to be deleted from cache")
	}
	cache.Set("key1", "value1")
	cache.Set("key2", "value2")
	cache.Clear()
	_, ok = cache.Get("key1")
	if ok {
		t.Error("expected cache to be cleared")
	}
}

func TestBuildKey(t *testing.T) {
	tests := []struct {
		resourceType string
		expected     string
	}{
		{"locations", "locations"},
		{"racks", "racks"},
		{"statuses", "statuses"},
	}
	for _, tt := range tests {
		got := BuildKey(tt.resourceType)
		if got != tt.expected {
			t.Errorf("BuildKey(%q) = %q, want %q", tt.resourceType, got, tt.expected)
		}
	}
}

type testItem struct {
	ID   *string
	Name string
}

func TestFindByName(t *testing.T) {
	cache, err := New(0)
	if err != nil {
		t.Fatalf("failed to create cache: %v", err)
	}
	defer cache.Close()

	id1 := "id-1" //nolint:goconst
	id2 := "id-2" //nolint:goconst
	items := []testItem{
		{ID: &id1, Name: "item1"},
		{ID: &id2, Name: "item2"},
	}

	cache.SetCollection("testitems", items)
	found, ok := FindByName(cache, "testitems", "item1", func(item testItem) string {
		return item.Name
	})
	if !ok {
		t.Fatal("expected to find item1")
	}
	if found.Name != "item1" {
		t.Errorf("expected item1, got %s", found.Name)
	}
	_, ok = FindByName(cache, "testitems", "item3", func(item testItem) string {
		return item.Name
	})
	if ok {
		t.Error("expected to not find item3")
	}
}

func TestFindByID(t *testing.T) {
	cache, err := New(0)
	if err != nil {
		t.Fatalf("failed to create cache: %v", err)
	}
	defer cache.Close()

	id1 := "id-1" //nolint:goconst
	id2 := "id-2" //nolint:goconst
	items := []testItem{
		{ID: &id1, Name: "item1"},
		{ID: &id2, Name: "item2"},
	}

	cache.SetCollection("testitems", items)
	found, ok := FindByID(cache, "testitems", "id-1", func(item testItem) *string { //nolint:goconst
		return item.ID
	})
	if !ok {
		t.Fatal("expected to find item with id-1")
	}
	if *found.ID != "id-1" { //nolint:goconst
		t.Errorf("expected id-1, got %s", *found.ID)
	}
	_, ok = FindByID(cache, "testitems", "id-3", func(item testItem) *string {
		return item.ID
	})
	if ok {
		t.Error("expected to not find item with id-3")
	}
}

func TestAddToCollection(t *testing.T) {
	cache, err := New(0)
	if err != nil {
		t.Fatalf("failed to create cache: %v", err)
	}
	defer cache.Close()

	id1 := "id-1" //nolint:goconst
	items := []testItem{{ID: &id1, Name: "item1"}}
	cache.SetCollection("testitems", items)
	id2 := "id-2" //nolint:goconst
	newItem := testItem{ID: &id2, Name: "item2"}
	AddToCollection(cache, "testitems", newItem)
	found, ok := FindByID(cache, "testitems", "id-2", func(item testItem) *string { //nolint:goconst
		return item.ID
	})
	if !ok {
		t.Fatal("expected to find newly added item")
	}
	if found.Name != "item2" {
		t.Errorf("expected item2, got %s", found.Name)
	}
}

func TestUpdateInCollection(t *testing.T) {
	cache, err := New(0)
	if err != nil {
		t.Fatalf("failed to create cache: %v", err)
	}
	defer cache.Close()

	id1 := "id-1" //nolint:goconst
	items := []testItem{{ID: &id1, Name: "item1"}}
	cache.SetCollection("testitems", items)
	updatedItem := testItem{ID: &id1, Name: "updated-item1"}
	UpdateInCollection(cache, "testitems", updatedItem, func(item testItem) bool {
		return item.ID != nil && *item.ID == "id-1" //nolint:goconst
	})
	found, ok := FindByID(cache, "testitems", "id-1", func(item testItem) *string { //nolint:goconst
		return item.ID
	})
	if !ok {
		t.Fatal("expected to find updated item")
	}
	if found.Name != "updated-item1" {
		t.Errorf("expected updated-item1, got %s", found.Name)
	}
}

func TestRemoveFromCollection(t *testing.T) {
	cache, err := New(0)
	if err != nil {
		t.Fatalf("failed to create cache: %v", err)
	}
	defer cache.Close()

	id1 := "id-1" //nolint:goconst
	id2 := "id-2" //nolint:goconst
	items := []testItem{
		{ID: &id1, Name: "item1"},
		{ID: &id2, Name: "item2"},
	}
	cache.SetCollection("testitems", items)
	RemoveFromCollection(cache, "testitems", func(item testItem) bool {
		return item.ID != nil && *item.ID == "id-1" //nolint:goconst
	})
	_, ok := FindByID(cache, "testitems", "id-1", func(item testItem) *string { //nolint:goconst
		return item.ID
	})
	if ok {
		t.Error("expected item to be removed")
	}
	_, ok = FindByID(cache, "testitems", "id-2", func(item testItem) *string { //nolint:goconst
		return item.ID
	})
	if !ok {
		t.Error("expected item2 to still exist")
	}
}
