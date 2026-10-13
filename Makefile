IMAGE ?= gfxreconstruct-test-env:local
REPOSITORY ?=
SOURCE_DIR ?=
SUITE ?= smoke
BUILD_TYPE ?= Release

# Conservative local defaults: protect an interactive workstation. CI invokes
# the scripts directly and therefore keeps its separate runner defaults.
BUILD_JOBS ?= 1
LOCAL_DOCKER_CPUS ?= 1.0
LOCAL_DOCKER_MEMORY ?= 4g
LOCAL_DOCKER_PIDS ?= 256
LAVAPIPE_THREADS ?= 1
LOCAL_DOCKER_LIMITS = --cpus="$(LOCAL_DOCKER_CPUS)" --memory="$(LOCAL_DOCKER_MEMORY)" --memory-swap="$(LOCAL_DOCKER_MEMORY)" --pids-limit="$(LOCAL_DOCKER_PIDS)"

.PHONY: image test help

help:
	@printf '%s\n' 'make test REPOSITORY=<GitHub URL with /tree/ref or /commit/SHA>'
	@printf '%s\n' 'make test SOURCE_DIR=/absolute/path/to/gfxreconstruct [BUILD_TYPE=Release] [BUILD_JOBS=1]'
	@printf '%s\n' 'Local limits: LOCAL_DOCKER_CPUS=1.0 LOCAL_DOCKER_MEMORY=4g LAVAPIPE_THREADS=1'

image:
	docker build --tag "$(IMAGE)" .

test: image
	mkdir -p out
	@if [ -n "$(SOURCE_DIR)" ]; then \
		test -d "$(SOURCE_DIR)" || { echo "SOURCE_DIR does not exist: $(SOURCE_DIR)" >&2; exit 2; }; \
		docker run --rm \
			$(LOCAL_DOCKER_LIMITS) \
			--user "$$(id -u):$$(id -g)" \
			--tmpfs /tmp:exec \
			--env HOME=/tmp \
			--env BUILD_JOBS="$(BUILD_JOBS)" \
			--env LP_NUM_THREADS="$(LAVAPIPE_THREADS)" \
			--volume "$$(pwd):/workspace/harness" \
			--volume "$(abspath $(SOURCE_DIR)):/workspace/source" \
			--workdir /workspace/harness \
			"$(IMAGE)" \
			./scripts/run-local-checkout.sh \
				--source-dir /workspace/source \
				--build-type "$(BUILD_TYPE)"; \
	else \
		docker run --rm \
			$(LOCAL_DOCKER_LIMITS) \
			--user "$$(id -u):$$(id -g)" \
			--tmpfs /tmp:exec \
			--env HOME=/tmp \
			--env BUILD_JOBS="$(BUILD_JOBS)" \
			--env LP_NUM_THREADS="$(LAVAPIPE_THREADS)" \
			--volume "$$(pwd):/workspace/harness" \
			--workdir /workspace/harness \
			"$(IMAGE)" \
			./scripts/run-tests.sh \
				--repository "$(REPOSITORY)" \
				--suite "$(SUITE)" \
				--build-type "$(BUILD_TYPE)"; \
	fi
