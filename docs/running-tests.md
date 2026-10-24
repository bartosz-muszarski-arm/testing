# Running gfxreconstruct tests

The optional `contracts` suite runs YAML-described capture/replay cases through
Chameleon. See [Chameleon contracts](contracts.md) for the case structure,
supplied-binary interface, and independent report validation.

The harness runs code from a requested **public GitHub repository** in an
Ubuntu 24.04 Docker environment. The same `scripts/run-tests.sh` command is
used by GitHub Actions and local development.

## GitHub Actions

Open **Actions → gfxreconstruct test → Run workflow** and provide a public GitHub URL that identifies the revision. Use either of these forms:

```text
https://github.com/owner/gfxreconstruct/tree/branch
https://github.com/owner/gfxreconstruct/commit/<SHA>
```

The run summary records the final resolved commit SHA, and logs/reports are
available as an Actions artifact.

## Local use

Install Docker, clone this harness, then run:

```bash
make test REPOSITORY=https://github.com/owner/gfxreconstruct/tree/branch
```

To test an existing local checkout in that same container, use the same target with `SOURCE_DIR`. The checkout is mounted writable because gfxreconstruct's CMake configuration creates source-tree lock/generated files; build products and logs stay in this harness repository.

```bash
make test SOURCE_DIR=/path/to/gfxreconstruct
```

Prepare submodules in the local checkout first:

```bash
git -C /path/to/gfxreconstruct submodule update --init --recursive
```

Set `BUILD_JOBS` to cap concurrent compiler jobs (default: `2`), for example `make test SOURCE_DIR=/path/to/gfxreconstruct BUILD_JOBS=1`. This value is passed to CMake as `--parallel N`, which is supported by the upstream CMake build.

`make test` builds the local test image and launches the canonical test entry
point used in CI. Outputs are written to `out/`:

```text
out/metadata.txt  requested source and resolved SHA
out/build.log     CMake configuration and build output
out/test.log      smoke-test output
```

The initial `smoke` suite configures and builds gfxreconstruct with CMake and
runs CTest when the selected revision exposes tests. It does not arbitrarily
run one of the built tools.

## Trust boundary

The requested revision is executed as untrusted code. This workflow is manual,
uses a read-only token, persists no checkout credentials, and must not be given
secrets or changed to run on privileged/self-hosted runners. Device- and
hardware-GPU tests should be added as separately provisioned workflows.
