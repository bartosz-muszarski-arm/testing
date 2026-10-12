#!/usr/bin/env bash
# Fetch the current default branch of tracetooltests and build its Vulkan tests.
set -euo pipefail

harness_dir=${1:?harness directory is required}
build_type=${2:?build type is required}
build_jobs=${BUILD_JOBS:-2}
[[ $build_jobs =~ ^[1-9][0-9]*$ ]] || {
    printf 'BUILD_JOBS must be a positive integer: %s\n' "$build_jobs" >&2
    exit 2
}

out_dir="$harness_dir/out"
source_dir="$out_dir/src/tracetooltests"
build_dir="$out_dir/build/tracetooltests-vulkan"
repository=https://github.com/ARM-software/tracetooltests.git

rm -rf "$source_dir" "$build_dir"
mkdir -p "$out_dir/src" "$out_dir/build"
git clone --depth 1 "$repository" "$source_dir"
git -C "$source_dir" submodule update --init --recursive --depth 1
source_sha=$(git -C "$source_dir" rev-parse HEAD)

{
    printf 'Repository: %s\n' "$repository"
    printf 'Resolved SHA: %s\n' "$source_sha"
    printf 'Configuration: Vulkan only (NO_GLES=1, NO_CL=1, NO_CHAMELEON=1)\n'
} | tee "$out_dir/tracetooltests-metadata.txt"

cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DCMAKE_BUILD_TYPE="$build_type" \
    -DNO_GLES=1 \
    -DNO_CL=1 \
    -DNO_CHAMELEON=1
cmake --build "$build_dir" --parallel "$build_jobs"

"$harness_dir/scripts/run-tracetooltests-lavapipe.sh" "$harness_dir" "$build_dir"
