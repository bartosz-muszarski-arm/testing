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
        libzstd-dev \
        libwayland-dev \
        libx11-dev \
        libxcb1-dev \
        libxcb-glx0-dev \
        libxcb-keysyms1-dev \
        libxcb-randr0-dev \
        libx11-xcb-dev \
        libglu1-mesa-dev \
        xorg-dev \
        xvfb \
        libxext-dev \
        libxi-dev \
        libxrandr-dev \
        mesa-vulkan-drivers \
        ninja-build \
        pkg-config \
        python3 \
        python3-pip \
        vulkan-tools \
        vulkan-validationlayers \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu 24.04 ships a Vulkan loader older than current tracetooltests. Build a pinned
# Khronos headers/loader pair so Vulkan 1.4 loader entry points link correctly.
ARG VULKAN_HEADERS_REV=b2ff582bfd4448d7b5f9ccd6a766b3ab322d59ed
ARG VULKAN_LOADER_REV=f866657ff687a36d767cd7783bab800e31ebafaa
RUN git clone --depth 1 https://github.com/KhronosGroup/Vulkan-Headers.git /tmp/Vulkan-Headers \
    && git -C /tmp/Vulkan-Headers fetch --depth 1 origin "$VULKAN_HEADERS_REV" \
    && git -C /tmp/Vulkan-Headers checkout --quiet --detach "$VULKAN_HEADERS_REV" \
    && cmake -S /tmp/Vulkan-Headers -B /tmp/Vulkan-Headers-build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --install /tmp/Vulkan-Headers-build \
    && git clone --depth 1 https://github.com/KhronosGroup/Vulkan-Loader.git /tmp/Vulkan-Loader \
    && git -C /tmp/Vulkan-Loader fetch --depth 1 origin "$VULKAN_LOADER_REV" \
    && git -C /tmp/Vulkan-Loader checkout --quiet --detach "$VULKAN_LOADER_REV" \
    && cmake -S /tmp/Vulkan-Loader -B /tmp/Vulkan-Loader-build -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF \
    && cmake --build /tmp/Vulkan-Loader-build --parallel 2 \
    && cmake --install /tmp/Vulkan-Loader-build \
    && ldconfig \
    && rm -rf /tmp/Vulkan-Headers /tmp/Vulkan-Headers-build /tmp/Vulkan-Loader /tmp/Vulkan-Loader-build

WORKDIR /workspace/harness
