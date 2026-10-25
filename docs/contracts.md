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
  types, named observations, and required replay properties.

Name cases after their distinguishing condition, using lowercase words separated
by hyphens. The case identity is `<group>/<case-name>`. The suite discovers
`tests/contracts/*/*.yaml`; each case uses the adjacent `workload.cpp`, without
a workload entry in YAML. The selected source is copied into each run's artifacts
before compilation. All cases use the same upload/readback/image workload.

Every case runs capture → optimize → replay. The runner invokes
`gfxrecon-optimize input.gfxr optimized.gfxr` from the selected tool build with
its default optimizations. Replay consumes `optimized.gfxr` when produced. If the
optimizer succeeds and explicitly reports that no unused resources were found
and no output will be created, replay consumes the original `input.gfxr` instead.
The report records this as `optimization.status: not_needed`, with the reason
and actual replay input. Optimizer failures, empty output, and unexplained
missing output stop the run. Optimization needs no case-specific YAML configuration.

`expect` lists the exact properties of the expected replay memory type. Property
order does not matter; additional or missing flags fail the contract. For example,
`[DEVICE_LOCAL]` requires local-only memory and rejects a host-visible local type. `observe` currently
supports `memory-type`. Every name must identify exactly one bound object during
each stage. Missing or ambiguous evidence is `INCONCLUSIVE`, not a pass. Wrong
properties or an unexpected effective driver configuration are `FAIL`. A workload
exit of 77 is a capability `SKIP`. Other compilation, capture, optimization,
replay, or timeout failures are `ERROR`.
Every non-PASS result makes the runner exit nonzero.

The case definitions and terminal/HTML reports use property names. Raw
observations retain the actual type indices. An expectation can still specify
`{memory-type-index: 0}` for a test specifically about index identity; reporting
expands it to properties and includes indices when equal flags would hide the
mismatch. Top-level `expect` applies to replay and covers every observed object.

Memory types are ordered as written. The runner creates one 1-GiB heap for
device-local types and one for non-local types; types in either group share that
heap. Protected types use separate 128-MiB heaps. This default keeps memory-type
selection cases readable without specifying heap topology. If heap mapping or
capacity is itself under test, each stage can explicitly declare `memory-heaps` as a list
of `{size: <bytes>, flags: [...]}` and `memory-types` as a list of
`{heap: <index>, properties: [...]}`. This preserves separate heaps with identical
flags and does not deduplicate memory types. Heap flags currently support
`DEVICE_LOCAL` or an empty list. Other device capabilities come from the base
profile. Per-resource memory requirement overrides are not implemented yet.

## Memory-selection cases

`buffer-memory-selection/unchanged-layout` exposes coherent host-visible,
cached noncoherent host-visible, lazy, and protected types in that order for
both capture and replay. All types carry DEVICE_LOCAL. The first three share
an ordinary heap; protected memory uses a separate heap.

The case lists only the ordered memory properties for capture and replay. The
runner supplies the ordinary/protected heap split, with synthetic non-limiting
capacities of 1 GiB ordinary and 128 MiB protected. It uses the
adjacent `workload.cpp` and expects coherent host-visible device-local memory
for `upload-buffer` (TRANSFER_SRC) and `optimal-image`, and cached noncoherent
host-visible device-local memory for `readback-buffer` (TRANSFER_DST). Capture bindings remain in the observation report.
There is no ordinary device-local-only type;
the image stays on coherent host-visible device-local memory. Lazy and protected types are exposed but not allocated.
The shared fixture writes a 1024-byte pattern to the coherent upload allocation
without an explicit flush, submits a buffer-to-image copy followed by an
image-to-buffer copy, waits for a fence, maps and invalidates readback memory,
and reads every byte. Capture relies on the upload allocation's HOST_COHERENT
property; replay must preserve the required visibility when restoring those
writes. Readback invalidation remains necessary for noncoherent memory.
Image layout transitions and a transfer-to-host barrier establish the required
ordering and visibility. Dedicated allocations are mapped and maintained in
full, avoiding noncoherent atom alignment issues with subranges.

By default, the workload compares the readback with the uploaded pattern and
fails on a mismatch. Chameleon records the image-copy commands without executing
them, so the contract runner explicitly passes `--no-verify`. That mode still
performs all Vulkan operations and CPU reads; only data comparison is disabled.
The command and the disabled verification are recorded in the run artifacts.
A contract PASS therefore establishes memory selection, not transferred contents.
Use an executing driver with the default workload mode to check the round trip.
The synchronization follows the [Vulkan synchronization examples](https://docs.vulkan.org/guide/latest/synchronization_examples.html).

`buffer-memory-selection/added-local-only-type` captures the same layout and
replays with device-local-only, coherent, lazy, cached, and protected types in
that order. It expects coherent upload memory, cached noncoherent readback
memory, and local-only image memory. This tests resource-specific selection when a local-only choice
becomes available and host-visible type indices change. The heap topology stays
the same; the new type shares the ordinary device-local heap.

`buffer-memory-selection/cached-before-coherent` retains the common capture
layout and replays with local-only, cached, lazy, coherent, and protected types.
Upload must select coherent memory, readback cached noncoherent memory, and
the optimal image local-only memory.

`buffer-memory-selection/combined-coherent-cached` uses the same order, but
the coherent replay type is also cached. Upload and readback must prefer that
combined type over cached-only memory; the image must select local-only memory.
Together, these cases distinguish reordered memory types from changes to their
cache and coherence properties. Chameleon runs observe selection and submitted
transfers; they do not verify transfer results or effective hardware cache
maintenance.

`buffer-memory-selection/coherent-type-becomes-cached` captures local-only,
coherent, lazy, cached, and protected types. Replay swaps the coherent and cached
positions. Upload must move to the coherent replay type even though its captured
index now refers to host-visible, bindable noncoherent memory. Readback must use
cached noncoherent memory, and the image must stay on local-only memory.

`buffer-memory-selection/cached-type-gains-coherence` uses the same capture
layout, but replay type 3 is both coherent and cached. Upload and readback must
select type 3, while the image stays on coherent host-visible device-local memory. Both cases use the same workload
and capture upload writes without an explicit flush. They exercise one upload
and submission; repeated reuse and effective hardware cache visibility require
additional coverage.

These expectations define the replay selection policy being tested. They are
not universal Vulkan requirements or a claim that the preferred type is fastest
on every device. Selection must also satisfy the resource's replay memory
requirements and supported data path.

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
report. `dependencies/chameleon-transfer-profile.patch` supplies the RGBA8
sampled/transfer format capabilities missing from the synthetic core profile.
GFXReconstruct needs no harness-specific changes.

At the end of a suite run, the terminal prints the case outcomes and selection
mismatches. Open `out/contracts-report.html` for the latest readable report:
it shows the selected revision or tool identity, capture/replay memory choices,
expectations, optimization decisions, and links to the raw evidence. A plain-text
copy is saved at `out/contracts-report.txt`. Each invocation also keeps its own
`report.html`, `summary.txt`, setup log, and case artifacts under a unique
`out/contract-tests/suite-*` directory. Missing case results appear as errors,
including when setup fails before capture. Opening the report does not rerun
validation or any tools.

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
- `result.json`: validation of those observations against the case expectations.

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
using the original trace when the optimizer explicitly reports no changes.
The `split-host-visible-types` case expects coherent host-visible memory for
upload, cached host-visible memory for readback, and device-local memory for the
optimal image. A replay implementation can fail a policy expectation while
still issuing legal Vulkan calls; a passing process alone does not satisfy the
contract.

Observations currently describe each object's final binding at instance teardown.
The ICD retains destroyed objects and allocation identities, so collection does
not depend on handle values or the order of names and binds. Repeated rebinding,
multiple instances/devices, and shared names need additional contract semantics.
These structural tests do not establish GPU output correctness.
