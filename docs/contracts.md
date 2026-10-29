# Chameleon contracts

Each directory under `tests/contracts/` groups cases using one shared workload:

```text
buffer-memory-selection/
  workload.cpp
  unchanged-layout.yaml
  added-local-only-type.yaml
  cached-before-coherent.yaml
  combined-coherent-cached.yaml
  coherent-type-becomes-cached.yaml
  cached-type-gains-coherence.yaml
  split-host-visible-types.yaml
```

- `workload.cpp`: a small, standalone Vulkan program using generic debug names.
- `<case-name>.yaml`: the purpose, base Chameleon profile, capture/replay memory
  types and named observations with their resource roles.

Name cases after their distinguishing condition, using lowercase words separated
by hyphens. The case identity is `<group>/<case-name>`. The suite discovers
`tests/contracts/*/*.yaml`; each case uses the adjacent `workload.cpp`, without
a workload entry in YAML. The selected source is copied into each run's artifacts
before compilation. All cases use the same upload/readback/image workload.

Every case runs capture → optimize → replay. The runner invokes
`gfxrecon-optimize input.gfxr optimized.gfxr` from the selected tool build with
its default optimizations. Replay consumes `optimized.gfxr` when produced. If the
optimizer exits successfully without creating an output file, replay consumes
the original `input.gfxr` instead. This decision does not depend on log wording.
The report records this as `optimization.status: completed_without_output`, with
the reason, optimizer log, and actual replay input. This status describes the
observed outcome; it does not assert that no optimization was needed. Nonzero
optimizer exits and empty or invalid output files stop the run.
Optimization needs no case-specific YAML configuration.

`observe` names the resource and its assessment role: `upload-unflushed`,
`readback`, or `optimal-image`. The upload role describes this workload's host
writes without an explicit capture-side flush; use it only when that is true.
The report compares observed capture and replay memory properties:

- **OPTIMAL**: the selection meets the role's preference: coherent for this
  upload, cached for readback, or device-local for an optimal image. This is a
  heuristic, not a measured performance result.
- **SUBOPTIMAL**: readback memory is not cached or the optimal image is not local.
  These are performance concerns and do not fail the run.
- **ISSUE**: a coherent, unflushed capture upload is rebound to noncoherent
  memory. The replay needs a flush or equivalent; these observations do not prove
  whether replay supplies one or whether the GPU output is incorrect.
- **INCONCLUSIVE**: evidence is missing or ambiguous, or a readback is not
  host-visible and the replay's data path is unknown.

Wrong effective driver configuration is `FAIL`; a missing required feature is
`SKIP`; a failed tool or workload is `ERROR`. These, `ISSUE`, and `INCONCLUSIVE`
make the runner exit nonzero. Legacy `memory-type` observations can still use
`expect` for explicit exact property or index assertions.

Memory types are ordered as written. The runner creates one 1-GiB heap for
device-local types and one for non-local types; types in either group share that
heap. Protected types use separate 128-MiB heaps. This default keeps memory-type
selection cases readable without specifying heap topology. If heap mapping or
capacity is itself under test, each stage can explicitly declare `memory-heaps` as a list
of `{size: <bytes>, flags: [...]}` and `memory-types` as a list of
`{heap: <index>, properties: [...]}`. This preserves separate heaps with identical
flags and does not deduplicate memory types. Heap flags currently support
`DEVICE_LOCAL` or an empty list. Other device capabilities come from the base
profile. Chameleon excludes lazy memory from buffers and non-transient images,
and separates protected and unprotected resource memory types. These rules apply
to existing-resource and maintenance4 requirement queries. Driver-specific
per-resource memory requirement overrides are not implemented yet.

## Memory-selection cases

`buffer-memory-selection/unchanged-layout` exposes coherent host-visible,
cached noncoherent host-visible, lazy, and protected types in that order for
both capture and replay. All types carry DEVICE_LOCAL. The first three share
an ordinary heap; protected memory uses a separate heap.

Each case lists ordered capture and replay properties and observes the same
three resources. The shared fixture writes a 1024-byte pattern to coherent
upload memory without an explicit flush, transfers it through an optimal image,
and invalidates and reads the readback buffer. Case names identify the memory
layout changes, including reordered types, a new local-only type, and changes
to cache and coherence properties. The scenarios assess the selections using
the role-specific rules above, rather than requiring an exact property list.

Chameleon records image-copy commands without executing them, so the contract
runner passes `--no-verify`: it checks structural observations, not transferred
contents. Use an executing driver with the default workload mode to check the
round trip. The synchronization follows the [Vulkan synchronization examples](https://docs.vulkan.org/guide/latest/synchronization_examples.html).

These cases assess externally observed memory selections. They do not prescribe
how a replayer chooses a type, prove a performance difference, or establish
coverage for other resource types and allocation paths.

## Run

Use the same Docker entry point locally and in the manual GitHub Actions workflow:

```bash
make test REPOSITORY=https://github.com/owner/gfxreconstruct/tree/branch SUITE=contracts
make test SOURCE_DIR=/path/to/gfxreconstruct SUITE=contracts
make test GFXR_PREFIX=/path/to/gfxreconstruct-build SUITE=contracts
```

The first two build GFXReconstruct using the existing build configuration. The
third consumes supplied tools and capture layer. Chameleon is built separately,
only targeting its full ICD. Its source revision is pinned in
`scripts/build-chameleon.sh`; `dependencies/chameleon-memory-report.patch` adds
effective memory properties and named resource bindings to its existing JSON
report. `dependencies/chameleon-memory-requirements.patch` applies the basic
lazy/protected resource eligibility rules.
`dependencies/chameleon-profile-identity.patch` supplies a stable synthetic device
name and ID so equivalent-environment contracts have explicit device identity.
`dependencies/chameleon-transfer-profile.patch` supplies the RGBA8
sampled/transfer format capabilities missing from the synthetic core profile.
GFXReconstruct needs no harness-specific changes.

At the end of a suite run, the terminal prints the case outcomes and assessment
reasons. Open `out/contracts-report.html` for the latest readable report:
it shows the selected revision or tool identity, capture/replay memory choices,
role-specific assessments, optimization decisions, and links to the raw evidence. A plain-text
copy is saved at `out/contracts-report.txt`, with a Markdown summary at
`out/contracts-report.md`. Each invocation also keeps its own
`report.html`, `summary.txt`, `summary.md`, setup log, and case artifacts under a unique
`out/contract-tests/suite-*` directory. Missing case results appear as errors,
including when setup fails before capture. Opening the report does not rerun
validation or any tools.

GitHub Actions displays the Markdown summary on the workflow run page, including
case outcomes, resource roles, capture/replay selections, assessment reasons,
and the trace selected for replay.
The summary links to the downloadable logs and reports artifact: extract it and
open `contracts-report.html` to browse the full report and its linked evidence.
Build metadata is available in a collapsible section. If the run fails before a
contract report is produced, the summary directs you to the build and test logs.

To use already prepared dependencies directly:

```bash
python3 scripts/contract.py run \
  --case tests/contracts/buffer-memory-selection/unchanged-layout.yaml \
  --gfxr-prefix /path/to/gfxreconstruct-build \
  --chameleon-icd out/dependencies/chameleon/chameleon_icd.json \
  --profiles out/dependencies/chameleon/source/share/chameleon/devices
```

The native runner requires a C++ compiler, Vulkan headers/loader, and PyYAML.
Dependencies are installed by the Dockerfile.
The image installs pinned Vulkan 1.4 headers and loader.
Ubuntu's Vulkan 1.3 loader drops the capture-side debug-name observations with
this ICD. Loaded capture, ICD, and loader libraries are verified and recorded.

## Evidence and validation

Each run creates a unique directory under `out/contract-tests/`, preserving the
case, workload, generated profiles, exact tool/library hashes, commands, logs,
original `input.gfxr`, and optimized `optimized.gfxr` when produced. `optimize.log`
records optimizer output. `observations.json` records the optimizer identity,
optimization outcome, selected replay filename, and hashes of the captured,
selected replay, and any optimized trace. Reports are kept separately:

- `capture_0.json` and `replay_0.json`: raw Chameleon observations.
- `observations.json`: normalized capture/replay environments and named resource
  bindings, saved before validation and without pass/fail judgments.
- `result.json`: assessments and validation of those observations.

The observations record that data comparison is disabled for the observation
driver. The capture-layer manifest uses an absolute library path; loader
diagnostics must confirm that exact library was initialized.

Validation can run again without executing Vulkan or any GFXR tools:

```bash
python3 scripts/contract.py validate --report out/contract-tests/<run>/observations.json
python3 -m unittest discover -s tests/harness -v
```

All memory-selection cases cover buffer/image creation, memory requirements,
allocation, binding, debug names, host mapping, readback invalidation, image layout
transitions, transfer commands, queue submission, and fence completion. They
exercise GFXR capture, optimization, and replay with `--memory-translation rebind`,
using the original trace when the optimizer exits successfully without creating output.
The `split-host-visible-types` case can flag a non-cached readback as
suboptimal while accepting coherent or combined coherent/cached memory. Its
unflushed upload must preserve visibility; a noncoherent replay selection is
reported as an issue requiring investigation, not proof of corrupted output.

Observations currently describe each object's final binding at instance teardown.
The ICD retains destroyed objects and allocation identities, so collection does
not depend on handle values or the order of names and binds. Repeated rebinding,
multiple instances/devices, and shared names need additional contract semantics.
These structural tests do not establish GPU output correctness.
