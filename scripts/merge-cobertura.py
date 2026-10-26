#!/usr/bin/env python3
"""Merge multiple Cobertura coverage XML files into a single report.

Replaces the unmaintained `cobertura-merge-globby` npm package, which calls
`util.isString()` -- a Node API removed in Node 24 -- and crashes on the
current GitHub Actions runner image.

Each input is a Cobertura `<coverage>` document whose real content lives under
`<packages>`. Merging concatenates every input's `<package>` elements into one
output document and recomputes the top-level line-rate / branch-rate from the
combined hit counts, which is what downstream consumers (e.g. orgoro/coverage)
read. Inputs that are missing or unparsable are skipped with a warning rather
than aborting the merge -- some projects (stestr-based) never emit a
coverage.xml, so the set of inputs is expected to vary.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _rate(covered: int, total: int) -> float:
    return covered / total if total else 0.0


def merge(paths: list[Path], output: Path) -> int:
    merged_packages: list[ET.Element] = []
    sources: list[str] = []

    lines_covered = lines_valid = 0
    branches_covered = branches_valid = 0
    parsed = 0

    for path in paths:
        if not path.is_file():
            print(f"warning: skipping missing coverage file: {path}", file=sys.stderr)
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            print(f"warning: skipping unparsable {path}: {exc}", file=sys.stderr)
            continue

        parsed += 1

        # Cobertura stores per-line/branch totals as attributes on <coverage>.
        # Accumulate them so the merged top-level rates stay accurate.
        lines_covered += int(root.get("lines-covered", 0))
        lines_valid += int(root.get("lines-valid", 0))
        branches_covered += int(root.get("branches-covered", 0))
        branches_valid += int(root.get("branches-valid", 0))

        for sources_el in root.findall("sources"):
            for source in sources_el.findall("source"):
                if source.text and source.text not in sources:
                    sources.append(source.text)

        for packages_el in root.findall("packages"):
            merged_packages.extend(packages_el.findall("package"))

    if parsed == 0:
        print(
            "error: no coverage files could be parsed; nothing to merge",
            file=sys.stderr,
        )
        return 1

    coverage = ET.Element("coverage")
    coverage.set("line-rate", f"{_rate(lines_covered, lines_valid):.4f}")
    coverage.set("branch-rate", f"{_rate(branches_covered, branches_valid):.4f}")
    coverage.set("lines-covered", str(lines_covered))
    coverage.set("lines-valid", str(lines_valid))
    coverage.set("branches-covered", str(branches_covered))
    coverage.set("branches-valid", str(branches_valid))
    coverage.set("version", "1.0")
    coverage.set("timestamp", "0")

    if sources:
        sources_el = ET.SubElement(coverage, "sources")
        for src in sources:
            ET.SubElement(sources_el, "source").text = src

    packages_out = ET.SubElement(coverage, "packages")
    for package in merged_packages:
        packages_out.append(package)

    tree = ET.ElementTree(coverage)
    ET.indent(tree, space="  ")
    output.write_bytes(
        b'<?xml version="1.0" ?>\n' + ET.tostring(coverage, encoding="unicode").encode()
    )
    print(
        f"merged {parsed} coverage file(s), "
        f"{len(merged_packages)} package(s) -> {output}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="path to write the merged coverage XML",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Cobertura coverage XML files to merge",
    )
    args = parser.parse_args(argv)
    return merge(args.inputs, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
