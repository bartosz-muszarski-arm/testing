FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Build and software-Vulkan prerequisites only. Hardware/device suites belong
# on separately provisioned runners.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
        libvulkan-dev \
        liblz4-dev \
        libwayland-dev \
        libx11-dev \
        libxcb1-dev \
        libxext-dev \
        libxi-dev \
        libxrandr-dev \
        mesa-vulkan-drivers \
        ninja-build \
        pkg-config \
        python3 \
        python3-pip \
        vulkan-tools \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/harness
