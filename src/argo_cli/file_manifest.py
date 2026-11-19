"""Validation and preview for Preassembly file_manifest.csv.

Rules from SDR User Guide > Accessioning > Preassembly >
"Accessioning complex content using a file manifest".
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from rich.tree import Tree

REQUIRED = ["druid", "filename", "resource_label", "sequence", "publish", "shelve", "preserve", "resource_type"]
RESOURCE_TYPES = {"video", "audio", "image", "file", "object", "media", "page", "3d"}
ROLES = {"transcription", "caption", "thumbnail", "annotations", "derivative", "master"}
BCP47_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
YES_NO = {"yes", "no"}


@dataclass
class FileManifest:
    path: Path
    headers: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def druids(self) -> list[str]:
        seen: list[str] = []
        for r in self.rows:
            if r["druid"] not in seen:
                seen.append(r["druid"])
        return seen


def load_and_validate(path: Path, manifest_druids: list[str]) -> FileManifest:
    fm = FileManifest(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fm.headers = [h.strip() for h in (reader.fieldnames or [])]
        fm.rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in reader]
    err, warn = fm.errors.append, fm.warnings.append

    # Header checks.
    missing = [c for c in REQUIRED if c not in fm.headers]
    if missing:
        err(f"missing required column(s): {', '.join(missing)}")
        return fm
    if fm.headers[0] != "druid":
        err("the druid column must be first (other columns can be in any order)")
    if fm.rows and fm.rows[0].get("filename", "").lower() == "filename":
        err("line 2 looks like the template's example row; delete it before submitting")

    # Row checks.
    for n, r in enumerate(fm.rows, start=2):
        r["druid"] = r["druid"].removeprefix("druid:")
        fn = r["filename"]
        if not fn:
            err(f"line {n}: filename is blank")
        if fn.endswith(".md5"):
            err(f"line {n}: don't list checksum files ({fn}); they're picked up automatically")
        for col in ("publish", "shelve", "preserve"):
            if r[col].lower() not in YES_NO:
                err(f"line {n}: {col} must be yes or no, got '{r[col]}'")
        if r["publish"].lower() != r["shelve"].lower():
            err(f"line {n}: publish and shelve must match ({fn})")
        if r["resource_type"] not in RESOURCE_TYPES:
            warn(f"line {n}: unusual resource_type '{r['resource_type']}' (documented: video, audio, image, file, object, media)")
        if not r["sequence"].isdigit():
            err(f"line {n}: sequence must be a whole number, got '{r['sequence']}'")
        role = r.get("role", "")
        if role and role not in ROLES:
            warn(f"line {n}: role '{role}' will be ignored (allowed: {', '.join(sorted(ROLES))})")
        if role == "caption" and not fn.lower().endswith(".vtt"):
            err(f"line {n}: caption files must be VTT ({fn})")
        lang = r.get("file_language", "")
        if lang and not BCP47_RE.match(lang):
            err(f"line {n}: file_language '{lang}' isn't a BCP-47 code (e.g. en, es, zh-Hant)")

    if any(not r["sequence"].isdigit() for r in fm.rows):
        return fm  # can't check ordering without numeric sequences

    # Ordering: each druid's rows together; sequences start at 1 and climb by 0 or 1.
    order: list[str] = []
    for n, r in enumerate(fm.rows, start=2):
        d = r["druid"]
        if order and order[-1] != d and d in order:
            err(f"line {n}: rows for {d} are split up; list each druid's files together")
        if not order or order[-1] != d:
            order.append(d)
    by_druid: dict[str, list[tuple[int, dict]]] = {}
    for n, r in enumerate(fm.rows, start=2):
        by_druid.setdefault(r["druid"], []).append((n, r))
    for d, items in by_druid.items():
        prev = 0
        labels: dict[int, tuple[str, str]] = {}
        for n, r in items:
            s = int(r["sequence"])
            if prev == 0 and s != 1:
                err(f"line {n}: {d} must start at sequence 1")
            elif s not in (prev, prev + 1) and prev != 0:
                err(f"line {n}: {d} sequence jumps from {prev} to {s} (use ascending order with no gaps, e.g. 1,1,2,3)")
            prev = s
            key = (r["resource_label"], r["resource_type"])
            if s in labels and labels[s] != key:
                err(f"line {n}: files in {d} resource {s} must share resource_label and resource_type")
            labels.setdefault(s, key)

    # Cross-check with manifest.csv.
    fm_set, m_set = set(fm.druids), set(manifest_druids)
    for d in sorted(m_set - fm_set):
        err(f"{d} is in manifest.csv but has no files in file_manifest.csv")
    for d in sorted(fm_set - m_set):
        err(f"{d} is in file_manifest.csv but not in manifest.csv")
    return fm


def resource_tree(fm: FileManifest, limit: int = 3) -> Tree:
    """Show how files would be grouped into resources on the Purl."""
    root = Tree(f"[bold]file_manifest.csv[/] → resources ({len(fm.rows)} files, {len(fm.druids)} object(s))")
    for d in fm.druids[:limit]:
        node = root.add(f"[cyan]{d}[/]")
        res: dict[str, Tree] = {}
        for r in (r for r in fm.rows if r["druid"] == d):
            s = r["sequence"]
            if s not in res:
                res[s] = node.add(f"[bold]{s}. {r['resource_label']}[/] [dim]({r['resource_type']})[/]")
            on_purl = r["publish"].lower() == "yes"
            flags = ("[green]purl[/]" if on_purl else "[dim]preservation only[/]")
            role = f" [magenta]{r['role']}[/]" if r.get("role") else ""
            res[s].add(f"{'🌐' if on_purl else '🔒'} {r['filename']}  {flags}{role}")
    if len(fm.druids) > limit:
        root.add(f"[dim]… {len(fm.druids) - limit} more object(s)[/]")
    return root
