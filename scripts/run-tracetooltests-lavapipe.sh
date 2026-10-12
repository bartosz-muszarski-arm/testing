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
    --output-junit "$out_dir/tracetooltests-lavapipe-junit.xml"
