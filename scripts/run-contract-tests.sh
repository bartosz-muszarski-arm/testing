#!/usr/bin/env bash
set -euo pipefail
harness_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
gfxr_prefix=${1:?GFXReconstruct build or installation directory is required}
mkdir -p "$harness_dir/out/contract-tests"
suite_dir=$(mktemp -d "$harness_dir/out/contract-tests/suite-XXXXXXXX")
# Keep summaries scoped to this invocation, including failures before capture.
finish() {
    local exit_status=$?
    trap - EXIT
    python3 "$harness_dir/scripts/contract_report.py" \
        --runs "$suite_dir" --exit-status "$exit_status" \
        --output "$harness_dir/out/contracts-report.html" || exit_status=1
    exit "$exit_status"
}
trap finish EXIT
: > "$suite_dir/cases.txt"
for case_file in "$harness_dir"/tests/contracts/*/*.yaml; do
    [[ -f $case_file ]] || continue
    printf '%s\n' "${case_file#"$harness_dir/tests/contracts/"}" >> "$suite_dir/cases.txt"
done
case "$gfxr_prefix" in
    "$harness_dir/out/build/gfxreconstruct"|"$harness_dir/out/build/local-gfxreconstruct")
        if [[ -f $harness_dir/out/metadata.txt ]]; then
            cp "$harness_dir/out/metadata.txt" "$suite_dir/metadata.txt"
        fi ;;
esac
python3 -m unittest discover -s "$harness_dir/tests/harness" -v 2>&1 | tee "$suite_dir/setup.log"
bash "$harness_dir/scripts/build-chameleon.sh" 2>&1 | tee -a "$suite_dir/setup.log"
dependency_dir="$harness_dir/out/dependencies/chameleon"
status=0
count=0
for case_file in "$harness_dir"/tests/contracts/*/*.yaml; do
    [[ -f $case_file ]] || continue
    count=$((count + 1))
    python3 "$harness_dir/scripts/contract.py" run \
        --case "$case_file" --gfxr-prefix "$gfxr_prefix" \
        --chameleon-icd "$dependency_dir/chameleon_icd.json" \
        --profiles "$dependency_dir/source/share/chameleon/devices" \
        --out "$suite_dir" || status=1
done
[[ $count -gt 0 ]] || { echo 'No contract cases found' >&2; exit 2; }
exit "$status"
