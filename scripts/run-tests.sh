#!/usr/bin/env bash
# Canonical test entry point for both GitHub Actions and local Docker use.
set -euo pipefail

usage() {
    printf 'Usage: %s --repository <GitHub /tree/ref or /commit/SHA URL> [--suite smoke] [--build-type Release]\n' "$0" >&2
}

harness_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
repository=''
suite=smoke
build_type=Release
while (($#)); do
    case "$1" in
        --repository) repository=${2:?missing value for --repository}; shift 2 ;;
        --suite) suite=${2:?missing value for --suite}; shift 2 ;;
        --build-type) build_type=${2:?missing value for --build-type}; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage; exit 2 ;;
    esac
done

[[ -n $repository ]] || { usage; exit 2; }
[[ $repository == https://github.com/*/tree/* || $repository == https://github.com/*/commit/* ]] || { printf "Repository must be a GitHub /tree/<branch> or /commit/<SHA> URL\n" >&2; exit 2; }
[[ $suite == smoke ]] || { printf 'Unsupported suite: %s\n' "$suite" >&2; exit 2; }
[[ $build_type =~ ^(Debug|Release|RelWithDebInfo|MinSizeRel)$ ]] || {
    printf 'Unsupported build type: %s\n' "$build_type" >&2; exit 2;
}

source_record=$("$harness_dir/scripts/resolve-source.sh" --repository "$repository")
IFS=$'\t' read -r source_repository source_ref <<< "$source_record"

out_dir="$harness_dir/out"
source_dir="$out_dir/src/gfxreconstruct"
build_dir="$out_dir/build/gfxreconstruct"
metadata="$out_dir/metadata.txt"
rm -rf "$source_dir" "$build_dir"
mkdir -p "$source_dir" "$build_dir"

git init --quiet "$source_dir"
git -C "$source_dir" remote add origin "https://github.com/${source_repository}.git"
git -C "$source_dir" fetch --depth=1 origin "$source_ref"
git -C "$source_dir" checkout --quiet --detach FETCH_HEAD
git -C "$source_dir" submodule update --init --recursive --depth 1
source_sha=$(git -C "$source_dir" rev-parse HEAD)

{
    printf 'Repository: https://github.com/%s\n' "$source_repository"
    printf 'Requested ref: %s\n' "$source_ref"
    printf 'Resolved SHA: %s\n' "$source_sha"
    printf 'Suite: %s\n' "$suite"
    printf 'Build type: %s\n' "$build_type"
    printf 'CMake: %s\n' "$(cmake --version | head -n1)"
} | tee "$metadata"

"$harness_dir/scripts/build-gfxreconstruct.sh" "$source_dir" "$build_dir" "$build_type" 2>&1 | tee "$out_dir/build.log"
"$harness_dir/scripts/run-smoke-tests.sh" "$build_dir" 2>&1 | tee "$out_dir/test.log"
"$harness_dir/scripts/build-tracetooltests-vulkan.sh" "$harness_dir" "$build_type" 2>&1 | tee "$out_dir/tracetooltests-build.log"
