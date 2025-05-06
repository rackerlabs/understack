# Makefile will understack go binary for multiple GOOS and GOARCH
#
# Output will be like this:
# understack_darwin_amd64/
#   └── understack
# understack_windows_amd64/
#   └── understack.exe
# understack_darwin_amd64.tar.gz
# understack_windows_amd64.zip
#
# package-all: will package folders into .tar.gz and for windows .zip

BINARY_NAME=understack

GOOS_LIST=linux darwin windows
GOARCH_LIST=386 amd64 arm64

BUILD_DIR=build

VERSION := $(shell git describe --tags --abbrev=0 --match "understack/v[0-9]*.[0-9]*.[0-9]*" 2>/dev/null || echo "dev")
COMMIT  := $(shell git rev-parse --short HEAD)
LDFLAGS := -ldflags="-s -w -X 'main.version=$(VERSION)' -X 'main.commit=$(COMMIT)'"

.PHONY: all
all: build build-all package-all

.PHONY: build
build:
	@echo "Building for current OS/Arch..."
	@mkdir -p $(BUILD_DIR)/$(BINARY_NAME)
	CGO_ENABLED=0 GOOS=$(shell go env GOOS) GOARCH=$(shell go env GOARCH) go build $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)/$(BINARY_NAME) .

.PHONY: build-all
build-all:
	@mkdir -p $(BUILD_DIR)
	@for GOOS in $(GOOS_LIST); do \
		for GOARCH in $(GOARCH_LIST); do \
			if [ "$$GOOS" = "darwin" ] && [ "$$GOARCH" = "386" ]; then \
				continue; \
			fi; \
			DIR=$(BUILD_DIR)/$(BINARY_NAME)_$$GOOS\_$$GOARCH; \
			EXT=$$([ "$$GOOS" = "windows" ] && echo ".exe" || echo ""); \
			OUTFILE=$$DIR/$(BINARY_NAME)$$EXT; \
			mkdir -p $$DIR; \
			echo "Building $$OUTFILE..."; \
			CGO_ENABLED=0 GOOS=$$GOOS GOARCH=$$GOARCH go build $() -o $$OUTFILE . || echo "Failed to build $$GOOS/$$GOARCH"; \
		done \
	done

# Loops over all the dirs in build/ folder
# for windows build zip
# else use .tar.gz
.PHONY: package-all
package-all:
	@echo "Packaging builds..."
	@cd $(BUILD_DIR) && for d in $(BINARY_NAME)_*; do \
		if echo $$d | grep -q "windows"; then \
			zip -qr "$$d.zip" "$$d"; \
		else \
			tar -czf "$$d.tar.gz" "$$d"; \
		fi \
	done


# Loops over *.zip and *.tar.gz in build/
# Uses sha256sum if available (Linux)
# Falls back to shasum -a 256 on macOS
# Outputs clean filenames without ./
# Result is stored in build/checksums.txt
.PHONY: checksums
checksums:
	@echo "Generating checksums..."
	@cd $(BUILD_DIR) && \
	for f in *.zip *.tar.gz; do \
		if command -v sha256sum >/dev/null 2>&1; then \
			sha256sum "$$f"; \
		else \
			shasum -a 256 "$$f"; \
		fi; \
	done | sort > checksums.txt

# remove build dir
.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)
