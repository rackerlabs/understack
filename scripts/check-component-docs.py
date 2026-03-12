#!/usr/bin/env python3
"""Validate that every ArgoCD Application template has a component doc page."""

from __future__ import annotations

from pathlib import Path
import sys

# Some templates are implementation details for a parent component and should
# map to the parent's docs page instead of requiring a separate file.
DOC_ALIASES: dict[str, str] = {
    "mariadb-operator-crds": "mariadb-operator",
    "prometheus-operator-crds": "monitoring",
}


def _component_name_from_template(path: Path) -> str:
    name = path.name
    prefix = "application-"
    suffix = ".yaml"
    if not (name.startswith(prefix) and name.endswith(suffix)):
        raise ValueError(f"Unexpected template filename: {name}")
    return name[len(prefix) : -len(suffix)]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    template_dir = repo_root / "charts" / "argocd-understack" / "templates"
    docs_dir = repo_root / "docs" / "deploy-guide" / "components"

    template_components = {
        _component_name_from_template(path)
        for path in template_dir.glob("application-*.yaml")
    }
    doc_components = {
        path.stem for path in docs_dir.glob("*.md") if path.stem != "index"
    }

    required_docs = {
        DOC_ALIASES.get(component, component) for component in template_components
    }
    missing_docs = sorted(required_docs - doc_components)
    if not missing_docs:
        print(
            "Component docs check passed: every application template has a matching "
            "docs/deploy-guide/components/<component>.md page."
        )
        return 0

    print("ERROR: Missing component docs for ArgoCD application templates:")
    for component in missing_docs:
        print(f"- {component}")

    print("\nCreate these files:")
    for component in missing_docs:
        print(f"- docs/deploy-guide/components/{component}.md")

    return 1


if __name__ == "__main__":
    sys.exit(main())
