from __future__ import annotations

from pathlib import Path

from vai_hold.decision_tree import mermaid_full_tree
from vai_hold.locator import build_locator, format_loc

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "Design" / "generated"


def write_artifacts() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "decision_tree.mmd").write_text(mermaid_full_tree(), encoding="utf-8")
    loc = build_locator()
    lines = ["# rule_id / event → file:function:line", ""]
    for key in sorted(loc):
        lines.append(f"## `{key}`")
        for row in loc[key][:8]:
            lines.append(f"- `{format_loc(row)}`")
        lines.append("")
    (OUT / "locator.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    write_artifacts()
    print(f"wrote {OUT}")
