#!/usr/bin/env bash
set -euo pipefail

source_dir=${1:?source directory is required}
build_dir=${2:?build directory is required}
build_type=${3:?build type is required}
build_jobs=${BUILD_JOBS:-2}
[[ $build_jobs =~ ^[1-9][0-9]*$ ]] || { printf "BUILD_JOBS must be a positive integer: %s\n" "$build_jobs" >&2; exit 2; }

cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DCMAKE_BUILD_TYPE="$build_type" \
    -DLZ4_ROOT=/usr \
    -DBUILD_TESTING=ON
cmake --build "$build_dir" --parallel "$build_jobs"
