package cache

import (
	"fmt"
	"time"

	"github.com/maypok86/otter/v2"
)

const DEFAULT_CACHE_SIZE = 70_000

// Cache provides a simple key-value cache for Nautobot resources
type Cache struct {
	store *otter.Cache[string, any]
}

// New creates a new cache instance
// New creates a new cache instance with the specified maximum size
func New(maxSize int) (*Cache, error) {
	if maxSize <= 0 {
		maxSize = DEFAULT_CACHE_SIZE
	}

	store, err := otter.New(&otter.Options[string, any]{
		MaximumSize:      maxSize,
		ExpiryCalculator: otter.ExpiryWriting[string, any](time.Hour),
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create cache: %w", err)
	}

	return &Cache{store: store}, nil
}

// Get retrieves a value from cache by key
func (c *Cache) Get(key string) (any, bool) {
	return c.store.GetIfPresent(key)
}

// Set stores a value in cache with the given key
func (c *Cache) Set(key string, value any) {
	c.store.Set(key, value)
}

// SetCollection stores a collection of items in cache
func (c *Cache) SetCollection(resourceType string, items any) {
	c.Set(BuildKey(resourceType), items)
}

// FindByName searches a cached collection for an item by name
func FindByName[T any](c *Cache, resourceType, name string, getName func(T) string) (T, bool) {
	var zero T
	val, ok := c.Get(BuildKey(resourceType))
	if !ok {
		return zero, false
	}

	items, ok := val.([]T)
	if !ok {
		return zero, false
	}

	for _, item := range items {
		if getName(item) == name {
			return item, true
		}
	}
	return zero, false
}

// FindByID searches a cached collection for an item by ID
func FindByID[T any](c *Cache, resourceType, id string, getID func(T) *string) (T, bool) {
	var zero T
	val, ok := c.Get(BuildKey(resourceType))
	if !ok {
		return zero, false
	}

	items, ok := val.([]T)
	if !ok {
		return zero, false
	}

	for _, item := range items {
		itemID := getID(item)
		if itemID != nil && *itemID == id {
			return item, true
		}
	}
	return zero, false
}

// AddToCollection adds a new item to a cached collection
func AddToCollection[T any](c *Cache, resourceType string, item T) {
	key := BuildKey(resourceType)
	val, ok := c.Get(key)
	if !ok {
		c.Set(key, []T{item})
		return
	}

	items, ok := val.([]T)
	if !ok {
		c.Set(key, []T{item})
		return
	}

	items = append(items, item)
	c.Set(key, items)
}

// UpdateInCollection updates an existing item in a cached collection
func UpdateInCollection[T any](c *Cache, resourceType string, updatedItem T, matchFunc func(T) bool) {
	key := BuildKey(resourceType)
	val, ok := c.Get(key)
	if !ok {
		return
	}

	items, ok := val.([]T)
	if !ok {
		return
	}

	// Find and update the item
	for i, item := range items {
		if matchFunc(item) {
			items[i] = updatedItem
			c.Set(key, items)
			return
		}
	}
}

// RemoveFromCollection removes an item from a cached collection
func RemoveFromCollection[T any](c *Cache, resourceType string, matchFunc func(T) bool) {
	key := BuildKey(resourceType)
	val, ok := c.Get(key)
	if !ok {
		return
	}

	items, ok := val.([]T)
	if !ok {
		return
	}

	// Filter out the item
	filtered := make([]T, 0, len(items))
	for _, item := range items {
		if !matchFunc(item) {
			filtered = append(filtered, item)
		}
	}
	c.Set(key, filtered)
}

// Delete removes a value from cache by key
func (c *Cache) Delete(key string) {
	c.store.Invalidate(key)
}

// Clear removes all entries from the cache
func (c *Cache) Clear() {
	c.store.InvalidateAll()
}

// Close closes the cache and releases resources
func (c *Cache) Close() {
	c.store.StopAllGoroutines()
}

// BuildKey creates a cache key for a resource collection
func BuildKey(resourceType string) string {
	return resourceType
}
