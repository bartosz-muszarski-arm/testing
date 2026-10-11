IMAGE ?= gfxreconstruct-test-env:local
REPOSITORY ?=
SOURCE_DIR ?=
SUITE ?= smoke
BUILD_TYPE ?= Release
BUILD_JOBS ?= 2

.PHONY: image test help

help:
	@printf '%s\n' 'make test REPOSITORY=<GitHub URL with /tree/ref or /commit/SHA>'
	@printf '%s\n' 'make test SOURCE_DIR=/absolute/path/to/gfxreconstruct [BUILD_TYPE=Release] [BUILD_JOBS=2]'

image:
	docker build --tag "$(IMAGE)" .

test: image
	mkdir -p out
	@if [ -n "$(SOURCE_DIR)" ]; then \
		test -d "$(SOURCE_DIR)" || { echo "SOURCE_DIR does not exist: $(SOURCE_DIR)" >&2; exit 2; }; \
		docker run --rm \
			--user "$$(id -u):$$(id -g)" \
			--tmpfs /tmp:exec \
			--env HOME=/tmp \
			--env BUILD_JOBS="$(BUILD_JOBS)" \
			--volume "$$(pwd):/workspace/harness" \
			--volume "$(abspath $(SOURCE_DIR)):/workspace/source" \
			--workdir /workspace/harness \
			"$(IMAGE)" \
			./scripts/run-local-checkout.sh \
				--source-dir /workspace/source \
				--build-type "$(BUILD_TYPE)"; \
	else \
		docker run --rm \
			--user "$$(id -u):$$(id -g)" \
			--tmpfs /tmp:exec \
			--env HOME=/tmp \
			--env BUILD_JOBS="$(BUILD_JOBS)" \
			--volume "$$(pwd):/workspace/harness" \
			--workdir /workspace/harness \
			"$(IMAGE)" \
			./scripts/run-tests.sh \
				--repository "$(REPOSITORY)" \
				--suite "$(SUITE)" \
				--build-type "$(BUILD_TYPE)"; \
	fi
