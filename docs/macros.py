from __future__ import annotations


def _as_list(value):
    if value in (None, False):
        return []
    if isinstance(value, list):
        return value
    return [value]


def _join_with_and(items):
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _render_sources(meta):
    source_text = meta.get("source_text")
    if source_text:
        return source_text

    parts = [f"Helm chart `{chart}`" for chart in _as_list(meta.get("charts"))]
    parts.extend(
        f"Kustomize path `{path}`" for path in _as_list(meta.get("kustomize_paths"))
    )
    if not parts:
        return ""
    return f"ArgoCD renders {_join_with_and(parts)}."


def _normalize_override(value, compat_modes):
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if value in compat_modes:
        return {"mode": compat_modes[value]}
    if isinstance(value, list):
        return {"mode": "values_files", "paths": value}
    raise ValueError(f"Unsupported deploy override value: {value!r}")


def _render_helm_override(deploy_overrides):
    override = _normalize_override(
        deploy_overrides.get("helm"),
        {
            False: "none",
            True: "values",
        },
    )
    if override is None:
        return ""

    mode = override.get("mode")
    if mode == "none":
        return "The current template does not read a deploy-repo `values.yaml` for this component."
    if mode == "values":
        return "The deploy repo contributes `values.yaml` for this component."
    if mode == "values_files":
        paths = [f"`{path}`" for path in _as_list(override.get("paths"))]
        return (
            f"The deploy repo contributes {_join_with_and(paths)} for this component."
        )

    raise ValueError(f"Unsupported helm deploy override mode: {mode!r}")


def _render_kustomize_override(deploy_overrides):
    override = _normalize_override(
        deploy_overrides.get("kustomize"),
        {
            False: "none",
            True: "second_source",
            "only": "only_source",
        },
    )
    if override is None:
        return ""

    mode = override.get("mode")
    if mode == "none":
        return "The current template does not apply a deploy-repo overlay directory for this component."
    if mode == "only_source":
        return (
            "The deploy repo overlay directory for this component is the only source for this "
            "Application, so `kustomization.yaml` and any referenced manifests are the final "
            "Application content."
        )
    if mode == "second_source":
        return (
            "The deploy repo overlay directory for this component is applied as a second source, "
            "so `kustomization.yaml` and any referenced manifests are part of the final Application."
        )
    raise ValueError(f"Unsupported kustomize deploy override mode: {mode!r}")


def define_env(env):
    env.variables["secrets_disclaimer"] = (
        "Use any secret delivery mechanism you prefer. "
        "The contract that matters is the final Kubernetes Secret or manifest shape described below."
    )

    @env.macro
    def component_argocd_builds():
        page = env.variables.get("page")
        meta = getattr(page, "meta", {}) or {}

        lines = []

        source_line = _render_sources(meta)
        if source_line:
            lines.append(f"- {source_line}")

        for line in _as_list(meta.get("argocd_extra")):
            lines.append(f"- {line}")

        deploy_overrides = meta.get("deploy_overrides") or {}

        helm_line = _render_helm_override(deploy_overrides)
        if helm_line:
            lines.append(f"- {helm_line}")

        kustomize_line = _render_kustomize_override(deploy_overrides)
        if kustomize_line:
            lines.append(f"- {kustomize_line}")

        return "\n".join(lines)
