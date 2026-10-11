#!/usr/bin/env bash
set -euo pipefail

build_dir=${1:?build directory is required}

if [[ -f "$build_dir/CTestTestfile.cmake" ]]; then
    ctest --test-dir "$build_dir" --output-on-failure
else
    printf '%s\n' 'No CTest test manifest was generated; build verification is the smoke test.'
fi
