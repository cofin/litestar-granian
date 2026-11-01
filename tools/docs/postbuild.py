"""Post-build generator for llms.txt, llms-full.txt, root brand assets, and flat .html redirect stubs."""

import argparse
import html
import json
import re
import shutil
import sys
import textwrap
import tomllib
from pathlib import Path
from typing import Any

__all__ = (
    "build_postbuild_artifacts",
    "compact_site_html",
    "emit_legacy_html_redirects",
    "generate_llms_files",
    "main",
    "sync_root_brand_assets",
)

_FRONTMATTER_PATTERN = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", re.DOTALL)
_FRONTMATTER_TITLE_PATTERN = re.compile(r"^[ \t]*title:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_SNIPPET_PATTERN = re.compile(r'^([ \t]*)--8<--[ \t]+"([^"\n]+)"[ \t]*$', re.MULTILINE)
_HEADING_PATTERN = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_HTML_BLOCK_PATTERN = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_PRE_BLOCK_PATTERN = re.compile(r"(<(?:pre|textarea)\b[^>]*>.*?</(?:pre|textarea)>)", re.IGNORECASE | re.DOTALL)
_LEADING_SPACE_PATTERN = re.compile(r"^[ \t]+", re.MULTILINE)
_TRAILING_SPACE_PATTERN = re.compile(r"[ \t]+$", re.MULTILINE)
_MULTI_NEWLINE_PATTERN = re.compile(r"\n{2,}")
_SECTION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_MIN_SNIPPET_RANGE_PARTS = 2
_FULL_SNIPPET_RANGE_PARTS = 3
_MIN_QUOTED_SCALAR_LENGTH = 2
_ROOT_BRAND_ASSETS: tuple[str, ...] = (
    "favicon.ico",
    "favicon.svg",
    "favicon.png",
    "favicon-16x16.png",
    "favicon-32x32.png",
    "favicon-48x48.png",
    "apple-touch-icon.png",
    "android-chrome-192x192.png",
    "android-chrome-512x512.png",
    "site.webmanifest",
)


def build_postbuild_artifacts(
    config_path: Path,
    docs_dir: Path,
    site_dir: Path,
) -> int:
    """Generate llms.txt, llms-full.txt, root favicons, and flat .html redirect files.

    Args:
        config_path: Path to ``zensical.toml``.
        docs_dir: Documentation source directory.
        site_dir: Built site output directory.

    Returns:
        Number of legacy HTML redirect stub files written.
    """
    compact_site_html(site_dir=site_dir)
    generate_llms_files(config_path=config_path, docs_dir=docs_dir, site_dir=site_dir)
    sync_root_brand_assets(docs_dir=docs_dir, site_dir=site_dir)
    return emit_legacy_html_redirects(config_path=config_path, site_dir=site_dir)


def compact_site_html(site_dir: Path) -> int:
    """Strip non-semantic Jinja indentation whitespace outside <pre> and <textarea> blocks in built HTML files.

    Args:
        site_dir: Built site directory containing ``.html`` files.

    Returns:
        Number of HTML files compacted.
    """
    if not site_dir.is_dir():
        return 0
    compacted = 0
    for html_file in sorted(site_dir.rglob("*.html")):
        raw = html_file.read_text(encoding="utf-8", errors="replace")
        parts = _PRE_BLOCK_PATTERN.split(raw)
        updated = "".join(
            part
            if part.lower().startswith(("<pre", "<textarea"))
            else _MULTI_NEWLINE_PATTERN.sub("\n", _TRAILING_SPACE_PATTERN.sub("", _LEADING_SPACE_PATTERN.sub("", part)))
            for part in parts
        )
        if updated != raw:
            html_file.write_text(updated, encoding="utf-8")
            compacted += 1
    return compacted


def sync_root_brand_assets(docs_dir: Path, site_dir: Path) -> int:
    """Copy favicon and web-manifest files from docs/assets into the root of site_dir.

    Args:
        docs_dir: Documentation source directory.
        site_dir: Built site directory.

    Returns:
        Number of brand asset files copied.
    """
    assets_dir = docs_dir / "assets"
    if not assets_dir.is_dir():
        return 0
    site_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for filename in _ROOT_BRAND_ASSETS:
        source = assets_dir / filename
        if source.is_file():
            shutil.copy2(source, site_dir / filename)
            copied += 1
    return copied


def generate_llms_files(config_path: Path, docs_dir: Path, site_dir: Path) -> None:
    """Write site/llms.txt and site/llms-full.txt ordered by zensical.toml navigation.

    Args:
        config_path: Path to ``zensical.toml``.
        docs_dir: Documentation source directory.
        site_dir: Built site output directory.
    """
    project = _load_config(config_path).get("project", {})
    site_name = str(project.get("site_name", "Documentation")).strip()
    site_description = str(project.get("site_description", "")).strip()
    site_url = str(project.get("site_url", "")).rstrip("/")
    sections = _collect_nav_sections(nav=project.get("nav", []), docs_dir=docs_dir)
    if not sections:
        sections = [
            (
                "Pages",
                [
                    (_extract_markdown_title(md_file), md_file.relative_to(docs_dir).as_posix())
                    for md_file in sorted(docs_dir.rglob("*.md"))
                ],
            )
        ]

    site_dir.mkdir(parents=True, exist_ok=True)
    header_lines: list[str] = [f"# {site_name}", ""]
    if site_description:
        header_lines.extend((f"> {site_description}", ""))

    llms_lines = list(header_lines)
    ordered_rel_paths = _append_llms_index_sections(
        llms_lines=llms_lines,
        sections=sections,
        docs_dir=docs_dir,
        site_url=site_url,
    )
    (site_dir / "llms.txt").write_text("\n".join(llms_lines).rstrip() + "\n", encoding="utf-8")

    full_chunks = list(header_lines)
    _append_llms_full_chunks(
        full_chunks=full_chunks,
        ordered_rel_paths=ordered_rel_paths,
        docs_dir=docs_dir,
        repo_root=config_path.resolve().parent,
        site_url=site_url,
    )
    (site_dir / "llms-full.txt").write_text("\n".join(full_chunks).rstrip() + "\n", encoding="utf-8")


def emit_legacy_html_redirects(config_path: Path, site_dir: Path) -> int:
    """Emit flat site/<legacy>.html redirect stubs for redirect_maps and directory index pages.

    Args:
        config_path: Path to ``zensical.toml``.
        site_dir: Built site directory.

    Returns:
        Total number of redirect HTML files written.
    """
    project = _load_config(config_path).get("project", {})
    site_url = str(project.get("site_url", "")).rstrip("/")
    redirect_maps = project.get("plugins", {}).get("redirects", {}).get("redirect_maps", {})
    if not isinstance(redirect_maps, dict):
        redirect_maps = {}

    written = _write_mapped_redirects(redirect_maps=redirect_maps, site_dir=site_dir, site_url=site_url)
    for index_file in sorted(site_dir.rglob("index.html")):
        if index_file == site_dir / "index.html":
            continue
        rel_dir = index_file.parent.relative_to(site_dir).as_posix()
        flat_stub = site_dir / f"{rel_dir}.html"
        if flat_stub.exists():
            continue
        target_path = f"/{rel_dir}/"
        canonical_url = f"{site_url}{target_path}" if site_url else target_path
        flat_stub.parent.mkdir(parents=True, exist_ok=True)
        flat_stub.write_text(
            _render_redirect_html(
                target_path=target_path, default_hash="", refresh_url=target_path, canonical_url=canonical_url
            ),
            encoding="utf-8",
        )
        written += 1

    return written


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for post-build documentation artifact generation.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit status code.
    """
    parser = argparse.ArgumentParser(description="Generate llms.txt, llms-full.txt, and legacy .html redirects.")
    parser.add_argument(
        "--config",
        "--zensical-config",
        dest="config",
        type=Path,
        default=Path("zensical.toml"),
        help="Path to zensical.toml.",
    )
    parser.add_argument("--docs-dir", type=Path, default=Path("docs"), help="Documentation source directory.")
    parser.add_argument("--site-dir", type=Path, default=Path("site"), help="Built site output directory.")
    args = parser.parse_args(argv)

    redirects_count = build_postbuild_artifacts(
        config_path=args.config,
        docs_dir=args.docs_dir,
        site_dir=args.site_dir,
    )
    sys.stdout.write(
        f"Generated {args.site_dir / 'llms.txt'}, {args.site_dir / 'llms-full.txt'}, "
        f"and {redirects_count} legacy .html redirect stub(s).\n"
    )
    return 0


def _append_llms_index_sections(
    *,
    llms_lines: list[str],
    sections: list[tuple[str, list[tuple[str, str]]]],
    docs_dir: Path,
    site_url: str,
) -> list[str]:
    """Append navigation section links to llms_lines and return deduplicated relative Markdown paths.

    Args:
        llms_lines: Output line buffer for ``llms.txt``.
        sections: Flattened navigation sections.
        docs_dir: Documentation source directory.
        site_url: Canonical base URL without trailing slash.

    Returns:
        Ordered list of unique relative Markdown paths.
    """
    ordered_rel_paths: list[str] = []
    seen_rel_paths: set[str] = set()
    for section_title, entries in sections:
        if not entries:
            continue
        llms_lines.extend((f"## {section_title}", ""))
        for label, rel_md in entries:
            clean_url = _doc_path_to_url(rel_md)
            full_url = f"{site_url}{clean_url}" if site_url else clean_url
            page_title = label or _resolve_title_for_rel_path(docs_dir, rel_md)
            llms_lines.append(f"- [{page_title}]({full_url})")
            if rel_md not in seen_rel_paths:
                seen_rel_paths.add(rel_md)
                ordered_rel_paths.append(rel_md)
        llms_lines.append("")
    return ordered_rel_paths


def _append_llms_full_chunks(
    *,
    full_chunks: list[str],
    ordered_rel_paths: list[str],
    docs_dir: Path,
    repo_root: Path,
    site_url: str,
) -> None:
    """Append expanded Markdown bodies for each page in ordered_rel_paths to full_chunks.

    Args:
        full_chunks: Output line buffer for ``llms-full.txt``.
        ordered_rel_paths: Relative Markdown file paths in nav order.
        docs_dir: Documentation source directory.
        repo_root: Repository root directory for snippet resolution.
        site_url: Canonical base URL without trailing slash.
    """
    for rel_md in ordered_rel_paths:
        source_path = docs_dir / rel_md
        if not source_path.is_file():
            continue
        clean_url = _doc_path_to_url(rel_md)
        full_url = f"{site_url}{clean_url}" if site_url else clean_url
        rendered = _expand_markdown_for_llms(
            markdown_text=source_path.read_text(encoding="utf-8"), repo_root=repo_root, page_url=full_url
        )
        full_chunks.extend(("---", f"Source: {full_url}", "---", "", rendered.strip(), ""))


def _write_mapped_redirects(*, redirect_maps: dict[Any, Any], site_dir: Path, site_url: str) -> int:
    """Write HTML redirect stubs for explicit redirect_maps entries.

    Args:
        redirect_maps: Mapping of legacy relative paths to target Markdown paths.
        site_dir: Built site directory.
        site_url: Canonical base URL without trailing slash.

    Returns:
        Number of mapped redirect files written.
    """
    written = 0
    for raw_old, raw_new in sorted(redirect_maps.items()):
        old_rel = str(raw_old).strip().lstrip("/")
        new_rel = str(raw_new).strip()
        if not old_rel or not new_rel:
            continue
        old_stem = old_rel.removesuffix(".md").removesuffix(".rst")
        if old_stem == "index" or old_stem.endswith("/index"):
            continue
        new_doc, sep, fragment = new_rel.partition("#")
        target_path = _doc_path_to_url(new_doc.lstrip("/"))
        default_hash = f"#{fragment}" if sep and fragment else ""
        refresh_url = f"{target_path}{default_hash}"
        canonical_base = f"{site_url}{target_path}" if site_url else target_path
        out_file = site_dir / f"{old_stem}.html"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(
            _render_redirect_html(
                target_path=target_path,
                default_hash=default_hash,
                refresh_url=refresh_url,
                canonical_url=f"{canonical_base}{default_hash}",
            ),
            encoding="utf-8",
        )
        written += 1
    return written


def _load_config(config_path: Path) -> dict[str, Any]:
    """Parse zensical.toml using stdlib tomllib.

    Args:
        config_path: Path to ``zensical.toml``.

    Returns:
        Parsed TOML dictionary.
    """
    return tomllib.loads(config_path.read_text(encoding="utf-8"))


def _collect_nav_sections(nav: Any, docs_dir: Path) -> list[tuple[str, list[tuple[str, str]]]]:
    """Flatten project.nav into top-level sections of (label, rel_md_path) pairs.

    Args:
        nav: Raw ``project.nav`` list from ``zensical.toml``.
        docs_dir: Documentation source directory.

    Returns:
        List of ``(section_title, entries)`` tuples.
    """
    if not isinstance(nav, list):
        return []

    sections: list[tuple[str, list[tuple[str, str]]]] = []
    root_items: list[tuple[str, str]] = []

    for item in nav:
        if isinstance(item, str):
            root_items.append((_resolve_title_for_rel_path(docs_dir, item), item))
        elif isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, str):
                    sections.append((str(key), [(str(key), value)]))
                elif isinstance(value, list):
                    nested: list[tuple[str, str]] = []
                    _collect_nested_nav_items(items=value, docs_dir=docs_dir, prefix="", out=nested)
                    sections.append((str(key), nested))

    if root_items:
        sections.insert(0, ("Overview", root_items))
    return sections


def _collect_nested_nav_items(items: list[Any], docs_dir: Path, prefix: str, out: list[tuple[str, str]]) -> None:
    """Recursively collect leaf Markdown routes from a nested nav list.

    Args:
        items: Nested navigation items.
        docs_dir: Documentation source directory.
        prefix: Breadcrumb prefix for nested subsections.
        out: Output list of ``(label, rel_md)`` pairs.
    """
    for entry in items:
        if isinstance(entry, str):
            title = _resolve_title_for_rel_path(docs_dir, entry)
            full_label = f"{prefix}{title}" if prefix else title
            out.append((full_label, entry))
        elif isinstance(entry, dict):
            for label, target in entry.items():
                if isinstance(target, str):
                    full_label = f"{prefix}{label}" if prefix else str(label)
                    out.append((full_label, target))
                elif isinstance(target, list):
                    next_prefix = f"{prefix}{label} - " if prefix else f"{label} - "
                    _collect_nested_nav_items(items=target, docs_dir=docs_dir, prefix=next_prefix, out=out)


def _resolve_title_for_rel_path(docs_dir: Path, rel_md: str) -> str:
    """Extract the H1 title from docs_dir / rel_md or derive a readable fallback.

    Args:
        docs_dir: Documentation source directory.
        rel_md: Docs-relative Markdown file path.

    Returns:
        Resolved human-readable title.
    """
    candidate = docs_dir / rel_md
    if candidate.is_file():
        return _extract_markdown_title(candidate)
    stem = Path(rel_md).stem
    if stem == "index":
        parent = Path(rel_md).parent.name
        return parent.replace("-", " ").replace("_", " ").title() or "Overview"
    return stem.replace("-", " ").replace("_", " ").title()


def _extract_markdown_title(md_file: Path) -> str:
    """Read the first Markdown H1 heading or YAML frontmatter title from md_file.

    Args:
        md_file: Markdown file path.

    Returns:
        Extracted title string.
    """
    frontmatter_title, body = _strip_yaml_frontmatter(md_file.read_text(encoding="utf-8"))
    match = _HEADING_PATTERN.search(body)
    if match:
        return match.group(1).strip()
    if frontmatter_title:
        return frontmatter_title
    stem = md_file.stem
    return stem.replace("-", " ").replace("_", " ").title()


def _strip_yaml_frontmatter(markdown_text: str) -> tuple[str | None, str]:
    """Strip leading YAML frontmatter and return an optional title scalar plus Markdown body.

    Args:
        markdown_text: Raw Markdown file contents.

    Returns:
        Tuple of ``(frontmatter_title, body_without_frontmatter)``.
    """
    match = _FRONTMATTER_PATTERN.match(markdown_text)
    if match is None:
        return None, markdown_text
    raw_frontmatter = match.group(1)
    body = markdown_text[match.end() :]
    title_match = _FRONTMATTER_TITLE_PATTERN.search(raw_frontmatter)
    if title_match is None:
        return None, body
    raw_title = title_match.group(1).strip()
    if len(raw_title) >= _MIN_QUOTED_SCALAR_LENGTH and raw_title[0] == raw_title[-1] and raw_title[0] in {'"', "'"}:
        raw_title = raw_title[1:-1].strip()
    return (raw_title or None), body


def _doc_path_to_url(rel_md: str) -> str:
    """Convert a docs-relative Markdown path to a directory-style URL path.

    Args:
        rel_md: Docs-relative path.

    Returns:
        Normalized directory URL path with leading and trailing slashes.
    """
    cleaned = rel_md.strip().lstrip("/")
    for suffix in (".md", ".rst", ".html"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break

    if cleaned in {"", "index"}:
        return "/"
    if cleaned.endswith("/index"):
        return f"/{cleaned[:-6]}/"
    return f"/{cleaned.rstrip('/')}/"


def _expand_markdown_for_llms(markdown_text: str, repo_root: Path, page_url: str) -> str:
    """Strip YAML frontmatter, expand --8<-- file snippets, and omit HTML widget blocks.

    Args:
        markdown_text: Raw Markdown text.
        repo_root: Repository root directory.
        page_url: Canonical page URL.

    Returns:
        Expanded plain Markdown suitable for ``llms-full.txt``.
    """
    _, body = _strip_yaml_frontmatter(markdown_text)

    def _replace_snippet(match: re.Match[str]) -> str:
        indent = match.group(1)
        spec = match.group(2).strip()
        path_part, line_slice, section_name = _split_snippet_spec(spec)
        snippet_path = (repo_root / path_part).resolve()
        if not snippet_path.is_relative_to(repo_root) or not snippet_path.is_file():
            return match.group(0)
        if snippet_path.suffix.lower() in {".html", ".htm"} and not path_part.startswith("docs/examples/"):
            return f"{indent}[Interactive HTML widget omitted; open {page_url} in a browser.]"
        content = snippet_path.read_text(encoding="utf-8")
        if section_name is not None:
            content = _extract_named_section(content, section_name)
        elif line_slice is not None:
            start_line, end_line = line_slice
            lines = content.splitlines()
            start_idx = max(start_line - 1, 0)
            end_idx = end_line if end_line is not None else len(lines)
            content = _strip_snippet_markers("\n".join(lines[start_idx:end_idx]))
        else:
            content = _strip_snippet_markers(content)
        return _indent_block(content.rstrip("\n"), indent)

    expanded = _SNIPPET_PATTERN.sub(_replace_snippet, body)
    return _HTML_BLOCK_PATTERN.sub("", expanded)


def _extract_named_section(content: str, section_name: str) -> str:
    """Extract and dedent lines inside --8<-- [start:<section_name>] .. [end:<section_name>].

    Args:
        content: Full snippet file text.
        section_name: Named section identifier.

    Returns:
        Dedented section text.
    """
    lines = content.splitlines()
    in_section = False
    extracted: list[str] = []
    start_tag = f"[start:{section_name}]"
    end_tag = f"[end:{section_name}]"

    for line in lines:
        stripped = line.strip()
        if "--8<--" in stripped and start_tag in stripped:
            in_section = True
            continue
        if "--8<--" in stripped and end_tag in stripped:
            in_section = False
            continue
        if in_section and not ("--8<--" in stripped and "[" in stripped and "]" in stripped):
            extracted.append(line)

    if not extracted:
        return ""
    joined = "\n".join(extracted)
    return textwrap.dedent(joined)


def _strip_snippet_markers(content: str) -> str:
    """Remove all --8<-- [start:...] and --8<-- [end:...] marker lines.

    Args:
        content: Raw snippet text.

    Returns:
        Snippet text with marker lines removed.
    """
    lines = [line for line in content.splitlines() if not ("--8<--" in line.strip() and "[" in line and "]" in line)]
    return "\n".join(lines)


def _indent_block(text: str, indent: str) -> str:
    """Prefix every non-empty line in text with indent.

    Args:
        text: Block of text to indent.
        indent: Leading whitespace prefix.

    Returns:
        Indented text block.
    """
    if not indent:
        return text
    return "\n".join(f"{indent}{line}" if line else "" for line in text.splitlines())


def _split_snippet_spec(spec: str) -> tuple[str, tuple[int, int | None] | None, str | None]:
    """Parse optional pymdownx.snippets path:start:end line range or path:section syntax.

    Args:
        spec: Raw snippet specification string.

    Returns:
        Tuple of ``(path, line_slice, section_name)``.
    """
    parts = spec.split(":")
    if len(parts) >= _MIN_SNIPPET_RANGE_PARTS:
        if parts[-1].isdigit():
            if len(parts) >= _FULL_SNIPPET_RANGE_PARTS and (parts[-2].isdigit() or parts[-2] == ""):
                start = int(parts[-2]) if parts[-2] else 1
                end = int(parts[-1])
                return ":".join(parts[:-2]), (start, end), None
            start = int(parts[-1])
            return ":".join(parts[:-1]), (start, None), None
        if _SECTION_NAME_PATTERN.match(parts[-1]):
            return ":".join(parts[:-1]), None, parts[-1]
    return spec, None, None


def _render_redirect_html(*, target_path: str, default_hash: str, refresh_url: str, canonical_url: str) -> str:
    """Render a minimal fragment-preserving HTML redirect document.

    Args:
        target_path: Redirect target path.
        default_hash: Optional fallback hash fragment.
        refresh_url: Meta refresh URL.
        canonical_url: Canonical link URL.

    Returns:
        Complete HTML redirect document string.
    """
    escaped_refresh = html.escape(refresh_url, quote=True)
    escaped_canonical = html.escape(canonical_url, quote=True)
    js_target = json.dumps(target_path)
    if default_hash:
        js_default_hash = json.dumps(default_hash)
        script_body = (
            f"const hash = window.location.hash || {js_default_hash}; window.location.replace({js_target} + hash);"
        )
    else:
        script_body = f"window.location.replace({js_target} + window.location.hash);"

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f'  <meta http-equiv="refresh" content="0; url={escaped_refresh}">\n'
        f'  <link rel="canonical" href="{escaped_canonical}">\n'
        "  <title>Redirecting...</title>\n"
        f"  <script>{script_body}</script>\n"
        "</head>\n"
        "<body>\n"
        f'  <p>Redirecting to <a href="{escaped_refresh}">{escaped_canonical}</a>.</p>\n'
        "</body>\n"
        "</html>\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
