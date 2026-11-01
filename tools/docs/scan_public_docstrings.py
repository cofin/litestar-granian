"""AST scanner for public docstring compiler leaks, @overload docstrings, and TypedDict/Struct field hygiene."""

import argparse
import ast
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

__all__ = (
    "DocstringLeakViolation",
    "OverloadDocstringViolation",
    "TypedDictDocstringViolation",
    "main",
    "scan_overload_docstrings",
    "scan_public_docstring_leaks",
    "scan_undocumented_typeddicts",
)

_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mypyc", re.compile(r"\bmypyc\b", re.IGNORECASE)),
    ("segfault", re.compile(r"\bsegfaults?\b", re.IGNORECASE)),
    ("segmentation fault", re.compile(r"\bsegmentation\s+faults?\b", re.IGNORECASE)),
    ("ABI boundary", re.compile(r"\babi\s+boundar(?:y|ies)\b", re.IGNORECASE)),
    ("Private/internal methods", re.compile(r"private/internal\s+methods", re.IGNORECASE)),
    ("cross-trait attribute", re.compile(r"cross-trait\s+attribute", re.IGNORECASE)),
)
_ATTRIBUTES_HEADER_PATTERN = re.compile(r"^\s*Attributes:\s*$", re.MULTILINE)
_OVERLOAD_DECORATORS: frozenset[str] = frozenset({"overload", "typing.overload", "typing_extensions.overload"})
_TYPEDDICT_BASES: frozenset[str] = frozenset({"TypedDict", "typing.TypedDict", "typing_extensions.TypedDict"})
_STRUCT_BASES: frozenset[str] = frozenset({
    "Struct",
    "msgspec.Struct",
    "BaseStruct",
    "CamelizedBaseStruct",
    "FrozenBaseStruct",
    "FrozenCamelizedStruct",
})


class DocstringLeakViolation(NamedTuple):
    """Public class, function, or method docstring containing internal compiler or layout notes."""

    path: Path
    line: int
    symbol: str
    matched_patterns: tuple[str, ...]

    def format(self) -> str:
        """Render a concise diagnostic line.

        Returns:
            Formatted diagnostic string.
        """
        joined = ", ".join(repr(item) for item in self.matched_patterns)
        return f"{self.path}:{self.line}: {self.symbol} leaks internal pattern(s) {joined}"


class OverloadDocstringViolation(NamedTuple):
    """Overload stub carrying a docstring instead of leaving documentation on the implementation."""

    path: Path
    line: int
    symbol: str

    def format(self) -> str:
        """Render a concise diagnostic line.

        Returns:
            Formatted diagnostic string.
        """
        return f"{self.path}:{self.line}: @overload {self.symbol} must not define a docstring"


class TypedDictDocstringViolation(NamedTuple):
    """Public or inherited TypedDict/Struct missing inline PEP 257 field docstrings or duplicating class Attributes."""

    path: Path
    line: int
    symbol: str
    missing_fields: tuple[str, ...]
    has_duplicate_class_attributes: bool

    def format(self) -> str:
        """Render a concise diagnostic line.

        Returns:
            Formatted diagnostic string.
        """
        details: list[str] = []
        if self.missing_fields:
            joined = ", ".join(self.missing_fields)
            details.append(f"missing PEP 257 field docstrings ({len(self.missing_fields)}): {joined}")
        if self.has_duplicate_class_attributes:
            details.append("duplicate class-level Attributes/field list in class docstring")
        return f"{self.path}:{self.line}: {self.symbol}: {'; '.join(details)}"


def scan_public_docstring_leaks(paths: Sequence[Path]) -> list[DocstringLeakViolation]:
    """Scan Python and stub files for public symbol docstrings containing compiler or internal-layout leaks.

    Args:
        paths: Files or directories to scan.

    Returns:
        Discovered docstring leak violations.
    """
    violations: list[DocstringLeakViolation] = []
    for file_path in _iter_python_files(paths):
        if file_path.name == "_typing.py":
            continue
        violations.extend(_scan_module_leaks(file_path))
    return violations


def scan_overload_docstrings(paths: Sequence[Path]) -> list[OverloadDocstringViolation]:
    """Scan Python and stub files for @overload-decorated functions or methods that carry docstrings.

    Args:
        paths: Files or directories to scan.

    Returns:
        Discovered overload docstring violations.
    """
    violations: list[OverloadDocstringViolation] = []
    for file_path in _iter_python_files(paths):
        violations.extend(_scan_module_overloads(file_path))
    return violations


def scan_undocumented_typeddicts(paths: Sequence[Path]) -> list[TypedDictDocstringViolation]:
    """Scan Python and stub files for TypedDict missing field docstrings or TypedDict/Struct duplicating Attributes.

    Args:
        paths: Files or directories to scan.

    Returns:
        Discovered TypedDict and Struct docstring violations.
    """
    violations: list[TypedDictDocstringViolation] = []
    for file_path in _iter_python_files(paths):
        violations.extend(_scan_module_typeddicts(file_path))
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for public docstring, overload, and TypedDict/Struct hygiene checks.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit status code.
    """
    parser = argparse.ArgumentParser(
        description="Verify public docstrings for compiler leaks, @overload docstrings, and TypedDict/Struct coverage."
    )
    parser.add_argument(
        "--check-leaks",
        action="store_true",
        help="Fail when public classes, functions, or methods leak compiler/ABI/layout notes.",
    )
    parser.add_argument("--check-overloads", action="store_true", help="Fail when @overload stubs define docstrings.")
    parser.add_argument(
        "--check-typeddicts",
        action="store_true",
        help="Fail when public TypedDict fields lack PEP 257 inline docstrings or duplicate class Attributes.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("litestar_granian")],
        help="Target files or directories to scan (defaults to litestar_granian).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    run_all = not (args.check_leaks or args.check_overloads or args.check_typeddicts)
    messages: list[str] = []

    if args.check_leaks or run_all:
        messages.extend(item.format() for item in scan_public_docstring_leaks(args.paths))
    if args.check_overloads or run_all:
        messages.extend(item.format() for item in scan_overload_docstrings(args.paths))
    if args.check_typeddicts or run_all:
        messages.extend(item.format() for item in scan_undocumented_typeddicts(args.paths))

    if messages:
        sys.stderr.write(f"Docstring hygiene check failed ({len(messages)} violation(s)):\n")
        for msg in messages:
            sys.stderr.write(f"  - {msg}\n")
        return 1

    sys.stdout.write("Docstring hygiene check passed.\n")
    return 0


def _iter_python_files(paths: Sequence[Path]) -> list[Path]:
    """Expand file and directory paths into a sorted deduplicated list of .py and .pyi files.

    Args:
        paths: Input file or directory paths.

    Returns:
        Sorted list of Python and stub files.
    """
    collected: set[Path] = set()
    for target in paths:
        if target.is_file() and target.suffix in {".py", ".pyi"}:
            collected.add(target)
        elif target.is_dir():
            collected.update(candidate for candidate in target.rglob("*.py") if candidate.is_file())
            collected.update(candidate for candidate in target.rglob("*.pyi") if candidate.is_file())
    return sorted(collected)


def _match_leak_patterns(docstring: str | None) -> tuple[str, ...]:
    """Return all matched compiler/layout leak labels in docstring.

    Args:
        docstring: Raw docstring text.

    Returns:
        Tuple of matched leak pattern labels.
    """
    if not docstring:
        return ()
    return tuple(label for label, pattern in _LEAK_PATTERNS if pattern.search(docstring))


def _scan_module_leaks(file_path: Path) -> list[DocstringLeakViolation]:
    """Inspect public top-level classes, functions, and public methods in file_path for docstring leaks.

    Args:
        file_path: Python file path.

    Returns:
        Discovered leak violations in the module.
    """
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    violations: list[DocstringLeakViolation] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            matched = _match_leak_patterns(ast.get_docstring(node))
            if matched:
                violations.append(
                    DocstringLeakViolation(path=file_path, line=node.lineno, symbol=node.name, matched_patterns=matched)
                )
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            matched = _match_leak_patterns(ast.get_docstring(node))
            if matched:
                violations.append(
                    DocstringLeakViolation(path=file_path, line=node.lineno, symbol=node.name, matched_patterns=matched)
                )
            violations.extend(_scan_class_member_leaks(file_path, node))

    return violations


def _scan_class_member_leaks(file_path: Path, class_node: ast.ClassDef) -> list[DocstringLeakViolation]:
    """Inspect public methods and inline attribute docstrings of class_node for docstring leaks.

    Args:
        file_path: Source file path.
        class_node: AST class definition node.

    Returns:
        Discovered leak violations on class members.
    """
    violations: list[DocstringLeakViolation] = []
    statements = class_node.body
    for idx, item in enumerate(statements):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_"):
            matched = _match_leak_patterns(ast.get_docstring(item))
            if matched:
                violations.append(
                    DocstringLeakViolation(
                        path=file_path,
                        line=item.lineno,
                        symbol=f"{class_node.name}.{item.name}",
                        matched_patterns=matched,
                    )
                )
        elif (
            isinstance(item, ast.AnnAssign)
            and isinstance(item.target, ast.Name)
            and not item.target.id.startswith("_")
            and idx + 1 < len(statements)
        ):
            next_stmt = statements[idx + 1]
            if (
                isinstance(next_stmt, ast.Expr)
                and isinstance(next_stmt.value, ast.Constant)
                and isinstance(next_stmt.value.value, str)
            ):
                matched = _match_leak_patterns(next_stmt.value.value)
                if matched:
                    violations.append(
                        DocstringLeakViolation(
                            path=file_path,
                            line=next_stmt.lineno,
                            symbol=f"{class_node.name}.{item.target.id}",
                            matched_patterns=matched,
                        )
                    )
    return violations


def _is_overload_decorated(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return whether node carries an @overload decorator.

    Args:
        node: AST function definition node.

    Returns:
        ``True`` if decorated with ``@overload``.
    """
    return any(ast.unparse(decorator) in _OVERLOAD_DECORATORS for decorator in node.decorator_list)


def _scan_module_overloads(file_path: Path) -> list[OverloadDocstringViolation]:
    """Inspect top-level functions and class methods in file_path for documented @overload stubs.

    Args:
        file_path: Python file path.

    Returns:
        Discovered overload docstring violations.
    """
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    violations: list[OverloadDocstringViolation] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_overload_decorated(node) and ast.get_docstring(node):
                violations.append(OverloadDocstringViolation(path=file_path, line=node.lineno, symbol=node.name))
        elif isinstance(node, ast.ClassDef):
            violations.extend(
                OverloadDocstringViolation(path=file_path, line=item.lineno, symbol=f"{node.name}.{item.name}")
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and _is_overload_decorated(item)
                and ast.get_docstring(item)
            )
    return violations


def _resolve_effective_typeddicts(classes: dict[str, ast.ClassDef]) -> list[ast.ClassDef]:
    """Resolve public TypedDict classes and any intra-module private TypedDict base classes they inherit.

    Args:
        classes: Mapping of class name to AST ClassDef node.

    Returns:
        Ordered list of effective TypedDict ClassDef nodes.
    """
    all_typeddicts: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, cls_node in classes.items():
            if name in all_typeddicts:
                continue
            if any(
                ast.unparse(base) in _TYPEDDICT_BASES or ast.unparse(base) in all_typeddicts for base in cls_node.bases
            ):
                all_typeddicts.add(name)
                changed = True

    effective: set[str] = {name for name in all_typeddicts if not name.startswith("_")}
    changed = True
    while changed:
        changed = False
        for name in tuple(effective):
            cls_node = classes[name]
            for base in cls_node.bases:
                base_name = ast.unparse(base)
                if base_name in all_typeddicts and base_name not in effective:
                    effective.add(base_name)
                    changed = True

    return [classes[name] for name in sorted(effective, key=lambda key: classes[key].lineno)]


def _resolve_public_structs(classes: dict[str, ast.ClassDef]) -> list[ast.ClassDef]:
    """Resolve public msgspec.Struct classes in the module.

    Args:
        classes: Mapping of class name to AST ClassDef node.

    Returns:
        Ordered list of public Struct ClassDef nodes.
    """
    all_structs: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, cls_node in classes.items():
            if name in all_structs:
                continue
            if any(ast.unparse(base) in _STRUCT_BASES or ast.unparse(base) in all_structs for base in cls_node.bases):
                all_structs.add(name)
                changed = True

    public_names = [name for name in all_structs if not name.startswith("_")]
    return [classes[name] for name in sorted(public_names, key=lambda key: classes[key].lineno)]


def _extract_typeddict_field_status(cls_node: ast.ClassDef) -> tuple[list[str], tuple[str, ...]]:
    """Return all annotated field names and the subset missing inline PEP 257 string docstrings.

    Args:
        cls_node: AST ClassDef node.

    Returns:
        Tuple of ``(all_fields, missing_fields)``.
    """
    statements = cls_node.body
    all_fields: list[str] = []
    missing_fields: list[str] = []

    for idx, stmt in enumerate(statements):
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        field_name = stmt.target.id
        if field_name.startswith("_"):
            continue
        all_fields.append(field_name)
        next_stmt = statements[idx + 1] if idx + 1 < len(statements) else None
        has_inline_doc = (
            isinstance(next_stmt, ast.Expr)
            and isinstance(next_stmt.value, ast.Constant)
            and isinstance(next_stmt.value.value, str)
            and bool(next_stmt.value.value.strip())
        )
        if not has_inline_doc:
            missing_fields.append(field_name)

    return all_fields, tuple(missing_fields)


def _has_duplicate_class_attributes(
    docstring: str | None, field_names: Sequence[str], *, check_field_list: bool
) -> bool:
    """Return whether docstring contains a redundant Attributes: header or manual field_name: list.

    Args:
        docstring: Class docstring text.
        field_names: Annotated field names on the class.
        check_field_list: Whether to also check for manual ``field:`` entries.

    Returns:
        ``True`` if duplicate attribute documentation is present.
    """
    if not docstring:
        return False
    if _ATTRIBUTES_HEADER_PATTERN.search(docstring):
        return True
    if not check_field_list:
        return False
    return any(
        re.search(rf"^\s*{re.escape(field_name)}\s*(?:\([^)\n]*\))?\s*:", docstring, re.MULTILINE)
        for field_name in field_names
    )


def _scan_module_typeddicts(file_path: Path) -> list[TypedDictDocstringViolation]:
    """Inspect public TypedDict and Struct schemas in file_path for missing or duplicated field docs.

    Args:
        file_path: Python source file path.

    Returns:
        Discovered TypedDict and Struct docstring violations.
    """
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    if not classes:
        return []

    violations: list[TypedDictDocstringViolation] = []
    for cls_node in _resolve_effective_typeddicts(classes):
        field_names, missing_fields = _extract_typeddict_field_status(cls_node)
        if not field_names:
            continue
        has_duplicate = _has_duplicate_class_attributes(ast.get_docstring(cls_node), field_names, check_field_list=True)
        if missing_fields or has_duplicate:
            violations.append(
                TypedDictDocstringViolation(
                    path=file_path,
                    line=cls_node.lineno,
                    symbol=cls_node.name,
                    missing_fields=missing_fields,
                    has_duplicate_class_attributes=has_duplicate,
                )
            )

    for cls_node in _resolve_public_structs(classes):
        field_names, _ = _extract_typeddict_field_status(cls_node)
        if not field_names:
            continue
        if _has_duplicate_class_attributes(ast.get_docstring(cls_node), field_names, check_field_list=False):
            violations.append(
                TypedDictDocstringViolation(
                    path=file_path,
                    line=cls_node.lineno,
                    symbol=cls_node.name,
                    missing_fields=(),
                    has_duplicate_class_attributes=True,
                )
            )
    return violations


if __name__ == "__main__":
    raise SystemExit(main())
