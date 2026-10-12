#!/usr/bin/env bash
# Run the smoke suite against a checkout mounted into the container.
set -euo pipefail

usage() {
    printf 'Usage: %s --source-dir <mounted gfxreconstruct checkout> [--build-type Release]\n' "$0" >&2
}

harness_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source_dir=''
build_type=Release
while (($#)); do
    case "$1" in
        --source-dir) source_dir=${2:?missing value for --source-dir}; shift 2 ;;
        --build-type) build_type=${2:?missing value for --build-type}; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage; exit 2 ;;
    esac
done

[[ -n $source_dir && -f $source_dir/CMakeLists.txt ]] || {
    printf 'Expected a gfxreconstruct source directory: %s\n' "$source_dir" >&2
    exit 2
}
[[ $build_type =~ ^(Debug|Release|RelWithDebInfo|MinSizeRel)$ ]] || {
    printf 'Unsupported build type: %s\n' "$build_type" >&2
    exit 2
}

# Missing submodules must be prepared on
# the host before invoking this mode.
if git -C "$source_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    source_sha=$(git -C "$source_dir" rev-parse HEAD)
    if git -C "$source_dir" submodule status --recursive | grep -q '^-'; then
        printf '%s\n' 'The local checkout has uninitialized submodules; run git submodule update --init --recursive on the host.' >&2
        exit 2
    fi
else
    source_sha=unknown
fi

out_dir="$harness_dir/out"
build_dir="$out_dir/build/local-gfxreconstruct"
rm -rf "$build_dir"
mkdir -p "$build_dir"
{
    printf 'Source: local checkout (%s)\n' "$source_dir"
    printf 'Resolved SHA: %s\n' "$source_sha"
    printf 'Suite: smoke\n'
    printf 'Build type: %s\n' "$build_type"
    printf 'CMake: %s\n' "$(cmake --version | head -n1)"
} | tee "$out_dir/metadata.txt"

"$harness_dir/scripts/build-gfxreconstruct.sh" "$source_dir" "$build_dir" "$build_type" 2>&1 | tee "$out_dir/build.log"
"$harness_dir/scripts/run-smoke-tests.sh" "$build_dir" 2>&1 | tee "$out_dir/test.log"
"$harness_dir/scripts/build-tracetooltests-vulkan.sh" "$harness_dir" "$build_type" 2>&1 | tee "$out_dir/tracetooltests-build.log"
