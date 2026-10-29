#!/usr/bin/env bash
# Build only the full Chameleon ICD, with structured memory observations.
set -euo pipefail
harness_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
dependency_dir="$harness_dir/out/dependencies/chameleon"
source_dir="$dependency_dir/source"
build_dir="$dependency_dir/build"
# CMake caches contain absolute paths. Preserve a native cache when Docker
# mounts the same checkout at a different path (and vice versa).
if [[ -f $build_dir/CMakeCache.txt ]]; then
    cached_source=$(sed -n 's/^CMAKE_HOME_DIRECTORY:INTERNAL=//p' "$build_dir/CMakeCache.txt")
    if [[ $cached_source != "$source_dir" ]]; then
        context=$(printf '%s' "$source_dir" | sha256sum)
        build_dir="$build_dir-${context:0:12}"
    fi
fi
revision=ee639aa879d110f99bdf17eb5f936e61a8dca6d3
jobs=${BUILD_JOBS:-2}
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo 'BUILD_JOBS must be a positive integer' >&2; exit 2; }
mkdir -p "$dependency_dir"
if [[ ! -d $source_dir/.git ]]; then
    git init "$source_dir"
    git -C "$source_dir" remote add origin https://github.com/ARM-software/tracetooltests.git
    git -C "$source_dir" fetch --depth 1 origin "$revision"
    git -C "$source_dir" checkout --detach FETCH_HEAD
fi
[[ $(git -C "$source_dir" rev-parse HEAD) == "$revision" ]] || {
    echo "Unexpected Chameleon dependency revision in $source_dir" >&2; exit 2;
}
git -C "$source_dir" submodule update --init --depth 1 \
    external/Vulkan-Headers external/SPIRV-Headers external/OpenCL-Headers external/OpenCL-Docs external/glm
patches=("$harness_dir/dependencies/chameleon-memory-report.patch"
         "$harness_dir/dependencies/chameleon-memory-requirements.patch"
         "$harness_dir/dependencies/chameleon-profile-identity.patch"
         "$harness_dir/dependencies/chameleon-transfer-profile.patch")
for patch in "${patches[@]}"; do
    if git -C "$source_dir" apply --check "$patch" 2>/dev/null; then
        git -C "$source_dir" apply "$patch"
    else
        git -C "$source_dir" apply --reverse --check "$patch"
    fi
done
{
    printf 'Repository: https://github.com/ARM-software/tracetooltests.git\nRevision: %s\n' "$revision"
    sha256sum "${patches[@]}"
} > "$dependency_dir/metadata.txt"
cmake -S "$source_dir" -B "$build_dir" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DNO_GLES=1 -DNO_CL=1
cmake --build "$build_dir" --target chameleon_icd --parallel "$jobs"
cp "$build_dir/chameleon_icd.json" "$dependency_dir/chameleon_icd.json"
