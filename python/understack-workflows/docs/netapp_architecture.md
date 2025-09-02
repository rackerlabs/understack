# NetApp Manager Architecture

## Overview

The NetApp Manager uses a layered architecture with dependency injection, providing maintainability, testability, and separation of concerns.

## Architecture Layers

### 1. NetAppManager (Orchestration Layer)

- **File**: `netapp_manager.py`
- **Purpose**: Orchestrates operations across multiple services
- **Key Features**:
    - Maintains all existing public method signatures
    - Delegates operations to appropriate service layers
    - Handles cross-service coordination (e.g., cleanup operations)
    - Manages dependency injection for all services

### 2. Service Layer

- **Files**: `netapp_svm_service.py`, `netapp_volume_service.py`, `netapp_lif_service.py`
- **Purpose**: Implements business logic and naming conventions for specific NetApp resource types
- **Key Features**:
    - Encapsulates business rules (e.g., SVM naming: `os-{project_id}`)
    - Handles resource-specific operations and validation
    - Provides clean interfaces for the orchestration layer
    - 100% test coverage with mocked dependencies

### 3. Client Abstraction Layer

- **File**: `netapp_client.py`
- **Purpose**: Provides a thin abstraction over the NetApp ONTAP SDK
- **Key Features**:
    - Converts between value objects and SDK objects
    - Handles low-level NetApp API interactions
    - Implements the NetAppClientInterface for testability
    - Manages SDK connection lifecycle

### 4. Infrastructure Components

#### Configuration Management

- **File**: `netapp_config.py`
- **Purpose**: Centralized configuration parsing and validation
- **Features**: Type-safe configuration with validation

#### Error Handling

- **File**: `netapp_error_handler.py`
- **Purpose**: Centralized error handling and logging
- **Features**: Context-aware error translation and structured logging

#### Value Objects

- **File**: `netapp_value_objects.py`
- **Purpose**: Immutable data structures for NetApp operations
- **Features**: Type-safe specifications and results for all operations

#### Custom Exceptions

- **File**: `netapp_exceptions.py`
- **Purpose**: Domain-specific exception hierarchy
- **Features**: Structured error information with context

## Dependency Flow

```text
NetAppManager
    ├── SvmService ──────┐
    ├── VolumeService ───┼── NetAppClient ── NetApp SDK
    ├── LifService ──────┘
    ├── NetAppConfig
    └── ErrorHandler
```

## Key Benefits

### 1. Maintainability

- Clear separation of concerns
- Single responsibility principle
- Dependency injection enables easy component replacement

### 2. Testability

- Each layer can be tested in isolation
- Service layer has 100% test coverage
- Mock-friendly interfaces reduce test complexity

### 3. API Stability

- All existing NetAppManager public methods unchanged
- Same method signatures and return values
- Existing code continues to work without modification

### 4. Extensibility

- New NetApp operations can be added at the appropriate layer
- Business logic changes isolated to service layer
- SDK changes isolated to client layer

## Usage Examples

### Basic Usage (Unchanged)

```python
# Existing code continues to work
manager = NetAppManager("/path/to/config.conf")
svm_name = manager.create_svm("project-123", "aggregate1")
volume_name = manager.create_volume("project-123", "1TB", "aggregate1")
```

### Advanced Usage with Dependency Injection

```python
# For testing or custom configurations
config = NetAppConfig("/custom/config.conf")
error_handler = ErrorHandler()
client = NetAppClient(config, error_handler)
svm_service = SvmService(client, error_handler)

# Use services directly if needed
svm_name = svm_service.create_svm("project-123", "aggregate1")
```

## Testing Strategy

### Unit Tests

- Each service tested with mocked NetAppClient
- Value objects tested for validation and immutability
- Configuration and error handling tested independently

### Integration Tests

- NetAppManager tested with mocked services
- Cross-service coordination tested (e.g., cleanup operations)
- API compatibility verified

## Potential Future Enhancements

The new architecture enables several future improvements:

1. **Async Operations**: Service layer can be enhanced with async/await
2. **Caching**: Client layer can add intelligent caching
3. **Metrics**: Error handler can emit metrics for monitoring
4. **Multi-tenancy**: Service layer can handle multiple NetApp clusters
5. **Configuration Hot-reload**: Config layer can support dynamic updates
