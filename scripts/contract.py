#!/usr/bin/env python3
"""Run Chameleon contracts, or validate their saved observations independently."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
FLAGS = {"DEVICE_LOCAL": 1, "HOST_VISIBLE": 2, "HOST_COHERENT": 4,
         "HOST_CACHED": 8, "LAZILY_ALLOCATED": 16, "PROTECTED": 32}


class CaseLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError("duplicate YAML key: " + str(key))
        result[key] = loader.construct_object(value_node)
    return result


CaseLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def load_case(path):
    case = yaml.load(path.read_text(), Loader=CaseLoader)
    if not isinstance(case, dict):
        raise ValueError("description must be a mapping")
    allowed = {"description", "profile", "capture", "replay", "observe", "expect"}
    if set(case) != allowed:
        raise ValueError("description requires exactly " + ", ".join(sorted(allowed)))
    if not all(isinstance(case[key], str) and case[key].strip() for key in ("description", "profile")):
        raise ValueError("description and profile must be strings")
    if Path(case["profile"]).name != case["profile"]:
        raise ValueError("profile must be a profile name")
    for stage in ("capture", "replay"):
        config = case[stage]
        if not isinstance(config, dict) or set(config) - {"memory-types", "memory-heaps", "arguments"}:
            raise ValueError(stage + ": unsupported configuration")
        if "memory-heaps" in config and config["memory-heaps"] is None:
            raise ValueError(stage + ": memory-heaps must be a nonempty list")
        memory_layout(config.get("memory-types"), config.get("memory-heaps"))
        if "arguments" in config and (stage != "replay" or
                not isinstance(config["arguments"], list) or
                not all(isinstance(x, str) for x in config["arguments"])):
            raise ValueError("arguments must be a list of replay arguments")
    if not isinstance(case["observe"], dict) or not case["observe"]:
        raise ValueError("observe must name at least one object")
    if any(not isinstance(name, str) or not name or prop != "memory-type"
           for name, prop in case["observe"].items()):
        raise ValueError("only named memory-type observations are supported")
    if not isinstance(case["expect"], dict) or set(case["expect"]) != set(case["observe"]):
        raise ValueError("expect must cover exactly the observed names")
    for expectation in case["expect"].values():
        if isinstance(expectation, list):
            check_properties(expectation)
        elif isinstance(expectation, dict) and set(expectation) == {"memory-type-index"}:
            index = expectation["memory-type-index"]
            if type(index) is not int or not 0 <= index < len(case["replay"]["memory-types"]):
                raise ValueError("expected memory-type-index is out of range")
        else:
            raise ValueError("expect a property list or {memory-type-index: N}")
    return case


def check_properties(properties):
    if not isinstance(properties, list) or not properties or any(
            not isinstance(p, str) or p not in FLAGS for p in properties):
        raise ValueError("expected a nonempty list of supported memory properties")
    if len(set(properties)) != len(properties):
        raise ValueError("duplicate memory property")
    if {"HOST_COHERENT", "HOST_CACHED"} & set(properties) and "HOST_VISIBLE" not in properties:
        raise ValueError("HOST_COHERENT/HOST_CACHED require HOST_VISIBLE")


def memory_layout(types, explicit_heaps=None):
    if not isinstance(types, list) or not 1 <= len(types) <= 32:
        raise ValueError("specify 1..32 memory types")
    if explicit_heaps is not None:
        if not isinstance(explicit_heaps, list) or not 1 <= len(explicit_heaps) <= 16:
            raise ValueError("specify 1..16 memory heaps")
        heaps, memory_types = [], []
        for heap in explicit_heaps:
            if not isinstance(heap, dict) or set(heap) != {"size", "flags"}:
                raise ValueError("each heap requires size and flags")
            if type(heap["size"]) is not int or not 0 < heap["size"] < 1 << 64:
                raise ValueError("heap size must be a positive uint64 byte count")
            flags = heap["flags"]
            if not isinstance(flags, list) or flags not in ([], ["DEVICE_LOCAL"]):
                raise ValueError("heap flags must be [] or [DEVICE_LOCAL]")
            heaps.append({"size": heap["size"], "flags": int(bool(flags))})
        for memory_type in types:
            if not isinstance(memory_type, dict) or set(memory_type) != {"heap", "properties"}:
                raise ValueError("explicit memory types require heap and properties")
            index = memory_type["heap"]
            if type(index) is not int or not 0 <= index < len(heaps):
                raise ValueError("memory type references an invalid heap index")
            check_properties(memory_type["properties"])
            if ("DEVICE_LOCAL" in memory_type["properties"]) != bool(heaps[index]["flags"]):
                raise ValueError("memory type and heap DEVICE_LOCAL flags must agree")
            memory_types.append({"heap_index": index,
                                 "property_flags": sum(FLAGS[p] for p in memory_type["properties"])})
        return {"memory_types": memory_types, "memory_heaps": heaps}
    # Default heaps are grouped by locality, with protected memory separate.
    heaps, indices, memory_types = [], {}, []
    for properties in types:
        check_properties(properties)
        local = "DEVICE_LOCAL" in properties
        protected = "PROTECTED" in properties
        group = (local, protected)
        if group not in indices:
            indices[group] = len(heaps)
            heaps.append({"size": 128 << 20 if protected else 1 << 30, "flags": int(local)})
        memory_types.append({"heap_index": indices[group],
                             "property_flags": sum(FLAGS[p] for p in properties)})
    return {"memory_types": memory_types, "memory_heaps": heaps}


def make_profile(base, destination, types, heaps=None):
    destination.mkdir()
    shutil.copyfile(base / "gpu.json", destination / "gpu.json")
    override = json.loads((base / "gpu_override.json").read_text())
    layout = memory_layout(types, heaps)
    memory = {
        "memoryTypeCount": len(types),
        "memoryTypes": [{"heapIndex": t["heap_index"], "propertyFlags": [
            "VK_MEMORY_PROPERTY_" + p + "_BIT" for p, flag in FLAGS.items() if t["property_flags"] & flag]}
            for t in layout["memory_types"]],
        "memoryHeapCount": len(layout["memory_heaps"]),
        "memoryHeaps": [{"size": h["size"], "flags":
            ["VK_MEMORY_HEAP_DEVICE_LOCAL_BIT"] if h["flags"] else []}
            for h in layout["memory_heaps"]],
    }
    override.setdefault("capabilities", {}).setdefault("device", {}).setdefault(
        "properties", {})["VkPhysicalDeviceMemoryProperties"] = memory
    write_json(destination / "gpu_override.json", override)


def normalize(raw, names):
    devices = raw.get("physical_devices", [])
    if len(devices) != 1:
        raise ValueError("expected exactly one observed physical device")
    physical = devices[0]
    result = {key: physical[key] for key in ("memory_types", "memory_heaps")}
    result["objects"] = {name: [] for name in names}
    for device in physical["devices"]:
        for binding in device["memory_bindings"]:
            name = binding.get("name")
            if name in result["objects"]:
                observed = dict(binding)
                if "memory_type_index" in binding:
                    index = binding["memory_type_index"]
                    if type(index) is not int or not 0 <= index < len(physical["memory_types"]):
                        raise ValueError("observed binding has an invalid memory type index")
                    memory_type = physical["memory_types"][index]
                    observed["properties"] = [p for p, flag in FLAGS.items()
                                              if memory_type["property_flags"] & flag]
                    observed["heap_index"] = memory_type["heap_index"]
                result["objects"][name].append(observed)
    return result


def validate(case, report):
    checks = []
    for stage in ("capture", "replay"):
        actual = report.get("stages", {}).get(stage)
        if actual is None:
            checks.append({"check": stage, "status": "INCONCLUSIVE", "reason": "missing stage"})
            continue
        expected = memory_layout(case[stage]["memory-types"], case[stage].get("memory-heaps"))
        topology_matches = all(actual.get(k) == v for k, v in expected.items())
        checks.append({"check": stage + "/environment",
                       "status": "PASS" if topology_matches else "FAIL"})
        expectations = case["expect"] if stage == "replay" else {}
        for name in case["observe"]:
            objects = actual.get("objects", {}).get(name, [])
            expectation = expectations.get(name)
            status, reason = "PASS", ""
            if (len(objects) != 1 or "allocation_uid" not in objects[0] or
                    type(objects[0].get("memory_type_index")) is not int or
                    not 0 <= objects[0]["memory_type_index"] < len(expected["memory_types"])):
                status, reason = "INCONCLUSIVE", "expected one uniquely named, bound object"
            elif isinstance(expectation, list) and not set(expectation) <= set(objects[0]["properties"]):
                status, reason = "FAIL", "required properties are absent"
            elif isinstance(expectation, dict) and objects[0]["memory_type_index"] != expectation["memory-type-index"]:
                status, reason = "FAIL", "unexpected memory type index"
            check = {"check": stage + "/" + name, "status": status, "reason": reason}
            if expectation is not None:
                check["expected"] = expectation
                field = "memory_type_index" if isinstance(expectation, dict) else "properties"
                check["observed"] = objects[0].get(field) if len(objects) == 1 else None
            checks.append(check)
    statuses = {check["status"] for check in checks}
    status = "FAIL" if "FAIL" in statuses else "INCONCLUSIVE" if "INCONCLUSIVE" in statuses else "PASS"
    if report.get("error"):
        status = "ERROR"
    elif report.get("skip") and status != "FAIL":
        status = "SKIP"
    return {"status": status, "checks": checks, "error": report.get("error"), "skip": report.get("skip")}


def execute(command, out, label, env=None):
    command = list(map(str, command))
    with (out / "commands.jsonl").open("a") as log:
        controlled_env = {k: v for k, v in (env or {}).items()
                          if k.startswith(("VK_", "GFXRECON_", "CHAMELEON_")) or
                          k in ("LD_LIBRARY_PATH", "LD_DEBUG")}
        log.write(json.dumps({"stage": label, "argv": command, "environment": controlled_env}) + "\n")
    print("+", " ".join(command), flush=True)
    with (out / (label + ".log")).open("w") as log:
        subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)


def identity(path):
    path = path.resolve(strict=True)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "sha256": digest.hexdigest()}


def find_tool(prefix, name, executable=True):
    for path in (prefix / name, prefix / "bin" / name, prefix / "lib" / name):
        if path.is_file() and (not executable or os.access(path, os.X_OK)):
            return path.resolve()
    candidates = sorted({p.resolve() for p in prefix.glob("**/" + name)
                         if p.is_file() and (not executable or os.access(p, os.X_OK))})
    if len(candidates) != 1:
        raise ValueError("expected one " + name + " in " + str(prefix))
    return candidates[0]


def find_layer_manifest(prefix, library):
    # Source builds also generate a staging manifest without an adjacent library.
    adjacent = library.with_name("VkLayer_gfxreconstruct.json")
    if adjacent.is_file():
        return adjacent.resolve()
    return find_tool(prefix, "VkLayer_gfxreconstruct.json", executable=False)


def run_case(args):
    case_path = args.case.resolve()
    case = load_case(case_path)
    case_id = case_path.parent.name + "/" + case_path.stem
    out_root = args.out.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=case_id.replace("/", "-") + "-", dir=out_root))
    print("Artifacts:", out, flush=True)
    shutil.copyfile(case_path, out / "description.yaml")
    shutil.copyfile(case_path.parent / "workload.cpp", out / "workload.cpp")
    report = {"case": case_id, "description": case["description"], "stages": {}}
    try:
        prefix = args.gfxr_prefix.resolve()
        replay = find_tool(prefix, "gfxrecon-replay")
        optimize = find_tool(prefix, "gfxrecon-optimize")
        library = find_tool(prefix, "libVkLayer_gfxreconstruct.so", executable=False)
        manifest_path = find_layer_manifest(prefix, library)
        manifest = json.loads(manifest_path.read_text())
        manifest["layer"]["library_path"] = str(library)
        layer_dir = out / "layer"
        layer_dir.mkdir()
        write_json(layer_dir / manifest_path.name, manifest)
        icd = args.chameleon_icd.resolve()
        icd_library = Path(json.loads(icd.read_text())["ICD"]["library_path"])
        if not icd_library.is_absolute():
            icd_library = icd.parent / icd_library
        profile = args.profiles.resolve() / case["profile"]
        report["inputs"] = {"replay": identity(replay), "optimize": identity(optimize),
                            "capture_layer": identity(library), "chameleon": identity(icd_library),
                            "capture_manifest": identity(manifest_path),
                            "base_profile": identity(profile / "gpu.json"),
                            "base_override": identity(profile / "gpu_override.json"),
                            "workload": identity(out / "workload.cpp")}
        metadata = icd.parent / "metadata.txt"
        if metadata.is_file():
            report["chameleon_build"] = metadata.read_text()
        # Vulkan/GFXR settings from the calling shell must not change this contract.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("VK_", "GFXRECON_", "CHAMELEON_"))}
        env.update(VK_DRIVER_FILES=str(icd), VK_ICD_FILENAMES=str(icd),
                   VK_LOADER_LAYERS_DISABLE="~implicit~",
                   CHAMELEON_DETERMINISTIC="1", CHAMELEON_VERBOSITY="1")
        execute([os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
                 "-Wno-missing-field-initializers", out / "workload.cpp", "-lvulkan",
                 "-o", out / "workload"], out, "compile")
        for stage in ("capture", "replay"):
            gpu = out / (stage + "-profile")
            make_profile(profile, gpu, case[stage]["memory-types"], case[stage].get("memory-heaps"))
            stage_env = env | {"CHAMELEON_GPU": str(gpu), "CHAMELEON_REPORT": str(out / stage),
                               "LD_DEBUG": "libs"}
            if stage == "capture":
                stage_env |= {"VK_LAYER_PATH": str(layer_dir),
                              "VK_INSTANCE_LAYERS": manifest["layer"]["name"],
                              "GFXRECON_CAPTURE_FILE": str(out / "input.gfxr"),
                              "GFXRECON_CAPTURE_FILE_TIMESTAMP": "false",
                              "GFXRECON_CAPTURE_FILE_FLUSH": "true"}
                # Chameleon observes transfers but does not execute image copies.
                report["data_verification"] = "disabled: observation driver does not execute image copies"
                command = [out / "workload", "--no-verify"]
            else:
                execute([optimize, out / "input.gfxr", out / "optimized.gfxr"], out, "optimize", env)
                optimized = out / "optimized.gfxr"
                no_change = "No unused resources detected. A new file will not be created."
                if optimized.is_file() and optimized.stat().st_size:
                    replay_input = optimized
                    report["optimization"] = {"status": "output_created", "replay_input": optimized.name}
                    report["inputs"]["optimized_trace"] = identity(optimized)
                elif not optimized.exists() and no_change in (out / "optimize.log").read_text():
                    replay_input = out / "input.gfxr"
                    report["optimization"] = {"status": "not_needed", "reason": no_change,
                                              "replay_input": replay_input.name}
                    print("Optimization not needed; replaying original capture:", replay_input, flush=True)
                else:
                    raise ValueError("optimization produced no trace")
                report["optimization"]["log"] = "optimize.log"
                report["inputs"]["captured_trace"] = identity(out / "input.gfxr")
                report["inputs"]["replay_trace"] = identity(replay_input)
                command = [replay, *case[stage].get("arguments", []), replay_input]
            execute(command, out, stage, stage_env)
            diagnostics = (out / (stage + ".log")).read_text()
            if "calling init: " + str(icd_library.resolve()) not in diagnostics:
                raise ValueError("loader did not confirm the selected Chameleon library")
            loaders = re.findall(r"calling init: ([^\n]*libvulkan\.so[^\n]*)", diagnostics)
            if len(loaders) != 1:
                raise ValueError("expected one Vulkan loader in runtime diagnostics")
            report["inputs"][stage + "_loader"] = identity(Path(loaders[0].strip()))
            if stage == "capture":
                if "calling init: " + str(library) not in diagnostics:
                    raise ValueError("loader did not confirm the selected capture library")
                if not (out / "input.gfxr").is_file():
                    raise ValueError("capture produced no trace")
            reports = list(out.glob(stage + "_*.json"))
            if len(reports) != 1:
                raise ValueError("expected one Chameleon report for " + stage)
            report["stages"][stage] = normalize(json.loads(reports[0].read_text()), case["observe"])
    except subprocess.CalledProcessError as error:
        if error.returncode == 77 and error.cmd[0] == str(out / "workload"):
            report["skip"] = "required feature unavailable: " + str(error)
        else:
            report["error"] = str(error)
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
    write_json(out / "observations.json", report)
    result = validate(case, report)
    write_json(out / "result.json", result)
    print(result["status"], out / "result.json", flush=True)
    for check in result["checks"]:
        if check["status"] != "PASS":
            print(check["status"], check["check"], check.get("reason", ""),
                  "expected:", check.get("expected"), "observed:", check.get("observed"))
    if report.get("error") or report.get("skip"):
        print(report.get("error") or report["skip"])
    return 0 if result["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--case", type=Path, required=True, help="path to a named case YAML file")
    run.add_argument("--gfxr-prefix", type=Path, required=True)
    run.add_argument("--chameleon-icd", type=Path, required=True)
    run.add_argument("--profiles", type=Path, required=True)
    run.add_argument("--out", type=Path, default=ROOT / "out/contract-tests")
    validation = commands.add_parser("validate")
    validation.add_argument("--report", type=Path, required=True)
    validation.add_argument("--description", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        return run_case(args)
    description = args.description or args.report.parent / "description.yaml"
    result = validate(load_case(description), json.loads(args.report.read_text()))
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
