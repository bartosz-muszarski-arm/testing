#!/usr/bin/env bash
# Run the Vulkan tracetooltests with Mesa Lavapipe as the only Vulkan ICD.
set -euo pipefail

harness_dir=${1:?harness directory is required}
build_dir=${2:?tracetooltests build directory is required}
build_jobs=${BUILD_JOBS:-2}
icd_path=${LAVAPIPE_ICD:-/usr/share/vulkan/icd.d/lvp_icd.json}

[[ -d $build_dir ]] || {
    printf 'tracetooltests build directory does not exist: %s\n' "$build_dir" >&2
    exit 2
}
[[ -r $icd_path ]] || {
    printf 'Lavapipe ICD is unavailable: %s\n' "$icd_path" >&2
    exit 2
}
[[ $build_jobs =~ ^[1-9][0-9]*$ ]] || {
    printf 'BUILD_JOBS must be a positive integer: %s\n' "$build_jobs" >&2
    exit 2
}

out_dir="$harness_dir/out"
runtime_dir=${XDG_RUNTIME_DIR:-/tmp/xdg-runtime}
mkdir -p "$out_dir" "$runtime_dir"
chmod 700 "$runtime_dir"
export XDG_RUNTIME_DIR=$runtime_dir
mkdir -p "$out_dir"

# VK_DRIVER_FILES makes the selected CPU driver deterministic, including on
# GitHub-hosted runners that may gain a hardware Vulkan ICD in the future.
export VK_DRIVER_FILES=$icd_path
export LIBGL_ALWAYS_SOFTWARE=1

{
    printf 'Driver: Mesa Lavapipe\n'
    printf 'ICD: %s\n' "$VK_DRIVER_FILES"
    printf 'CTest jobs: %s\n' "$build_jobs"
} | tee "$out_dir/lavapipe-metadata.txt"

vulkaninfo > "$out_dir/lavapipe-vulkaninfo.txt"

# tracetooltests uses exit code 77 for unsupported requirements; its CTest
# metadata translates those outcomes to skips. Do not enable NULL_RUN: real
# output verification is the purpose of this software-rasterizer run.
ctest --test-dir "$build_dir" \
    --output-on-failure \
    --parallel "$build_jobs" \
    --timeout 120 \
    --exclude-regex '^vulkan_host_image_copy$' \
    --output-junit "$out_dir/tracetooltests-lavapipe-junit.xml"

# Ubuntu 24.04's validation layer only supports Vulkan 1.3. It rejects the
# Vulkan 1.4 feature structure used by this test before the driver receives
# it, although Lavapipe supports the feature and the test passes normally.
# Keep validation enabled for the rest of the suite and run this one Vulkan
# 1.4 test directly without that incompatible layer.
printf '%s\n' \
    'vulkan_host_image_copy: run without VK_LAYER_KHRONOS_validation (Ubuntu 24.04 layer is Vulkan 1.3)' \
    | tee "$out_dir/tracetooltests-validation-exceptions.txt"
env -u VK_INSTANCE_LAYERS "$build_dir/vulkan_host_image_copy" \
    2>&1 | tee "$out_dir/vulkan_host_image_copy.log"
