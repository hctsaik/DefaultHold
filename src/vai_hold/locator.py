"""Scan source for rule_id / Event sites → file:function:line."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parent


def _walk_py() -> list[Path]:
    skip = {"locator.py", "decision_tree.py", "investigate.py"}
    return [
        p
        for p in SRC_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts and p.name not in skip
    ]


def build_locator() -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for path in _walk_py():
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        rel = path.relative_to(SRC_ROOT.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            keys: list[str] = []
            for kw in node.keywords:
                if kw.arg in {"rule_id"} and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    keys.append(kw.value.value)
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr and isinstance(func.value, ast.Name):
                if func.value.id == "Event":
                    keys.append(f"event:{func.attr}")
            for arg in node.args:
                if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "Event":
                    keys.append(f"event:{arg.attr}")
            if not keys:
                continue
            fn = _enclosing_function(tree, node.lineno)
            loc = {"file": rel, "function": fn, "line": node.lineno}
            for k in keys:
                found.setdefault(k, []).append(loc)
        # last_rule_id = "A2-02"
        for i, line in enumerate(text.splitlines(), 1):
            if 'last_rule_id = "' in line or "last_rule_id = '" in line:
                start = line.find('"')
                if start < 0:
                    start = line.find("'")
                if start >= 0:
                    end = line.find(line[start], start + 1)
                    rid = line[start + 1 : end]
                    if rid.startswith("A") or rid.startswith("D"):
                        found.setdefault(rid, []).append(
                            {"file": rel, "function": _enclosing_function(tree, i), "line": i}
                        )
    return found


def format_loc(entry: dict[str, Any]) -> str:
    return f"{entry['file']}:{entry['function']}:{entry['line']}"


def first_loc(locator: dict[str, list[dict[str, Any]]], *keys: str, prefer: str | None = None) -> str:
    def rank(row: dict[str, Any]) -> tuple:
        f = row["file"]
        if prefer and prefer in f:
            hit = 0
        elif any(x in f for x in ("usecases", "domain", "pipelines")):
            hit = 1
        else:
            hit = 2
        return (hit, f, row["line"])

    for k in keys:
        if not k:
            continue
        rows = locator.get(k) or []
        if rows:
            return format_loc(sorted(rows, key=rank)[0])
    return ""


def _enclosing_function(tree: ast.AST, lineno: int) -> str:
    name = "module"
    best = -1
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= lineno <= end and node.lineno >= best:
                name = node.name
                best = node.lineno
    return name
