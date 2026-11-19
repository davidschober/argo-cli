"""Shared output helpers: fake progress, the 'would have done' panel, druid parsing."""

from __future__ import annotations

import random
import re
import sys
import time
from pathlib import Path

import click
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from .docs import DOCS

console = Console()

# Druids: 2 letters, 3 digits, 2 letters, 4 digits; no vowels and no 'l'.
DRUID_RE = re.compile(r"^(druid:)?([b-df-hjkmnp-tv-z]{2}\d{3}[b-df-hjkmnp-tv-z]{2}\d{4})$")
_DRUID_LETTERS = "bcdfghjkmnpqrstvwxyz"


def fast_mode() -> bool:
    ctx = click.get_current_context(silent=True)
    return bool(ctx and ctx.find_root().obj and ctx.find_root().obj.get("fast"))


def fake_druid() -> str:
    l = lambda n: "".join(random.choice(_DRUID_LETTERS) for _ in range(n))  # noqa: E731
    d = lambda n: "".join(random.choice("0123456789") for _ in range(n))  # noqa: E731
    return f"druid:{l(2)}{d(3)}{l(2)}{d(4)}"


def normalize_druid(value: str) -> tuple[str, bool]:
    """Return (druid-with-prefix, is_valid)."""
    v = value.strip()
    m = DRUID_RE.match(v)
    if m:
        return f"druid:{m.group(2)}", True
    return v, False


def collect_druids(targets: tuple[str, ...]) -> list[str]:
    """Targets can be druids or files (.txt one per line, .csv with a 'druid' column)."""
    import csv

    druids: list[str] = []
    for t in targets:
        if t == "-":  # read druids piped in on stdin, e.g. from `argo find --format druids`
            druids += [ln.strip() for ln in sys.stdin if ln.strip()]
            continue
        p = Path(t)
        if p.is_file():
            if p.suffix.lower() == ".csv":
                with p.open(newline="") as fh:
                    reader = csv.DictReader(fh)
                    col = next((h for h in (reader.fieldnames or []) if h.lower() == "druid"), None)
                    if not col:
                        raise click.BadParameter(f"{p} has no 'druid' column")
                    druids += [r[col] for r in reader if r.get(col)]
            else:
                druids += [ln.strip() for ln in p.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
        else:
            druids.append(t)

    out, bad = [], []
    for d in druids:
        norm, ok = normalize_druid(d)
        out.append(norm)
        if not ok:
            bad.append(norm)
    if bad:
        console.print(
            f"[yellow]⚠ {len(bad)} value(s) don't look like druids "
            f"(expected e.g. druid:bc123df4567): {', '.join(bad[:5])}{' …' if len(bad) > 5 else ''}[/]"
        )
    return out


def fake_progress(label: str, items: list[str], *, per_item: tuple[float, float] = (0.05, 0.25)) -> None:
    """Show a progress bar that pretends to work through items."""
    fast = fast_mode()
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("[dim]{task.fields[current]}"),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(label, total=len(items), current="")
        for item in items:
            progress.update(task, current=str(item)[:40])
            if not fast:
                time.sleep(random.uniform(*per_item))
            progress.advance(task)
        progress.update(task, current="done")


def fake_steps(steps: list[str], *, delay: tuple[float, float] = (0.3, 0.8)) -> None:
    """Spinner that walks through named phases."""
    fast = fast_mode()
    with console.status("") as status:
        for s in steps:
            status.update(f"[cyan]{s}…")
            if not fast:
                time.sleep(random.uniform(*delay))
            console.print(f"  [green]✓[/] {s}")


def would_have(doc_key: str, title: str, actions: list[str], *, notes: list[str] | None = None) -> None:
    """The POC's punchline: explain what would have happened and where to read more."""
    body: list = [Text("This is a POC. Nothing was sent to SDR. A real run would have:\n", style="italic")]
    for i, a in enumerate(actions, 1):
        body.append(Text.from_markup(f"  [bold]{i}.[/] {a}"))
    if notes:
        body.append(Text(""))
        for n in notes:
            body.append(Text.from_markup(f"  [yellow]•[/] {n}"))
    body.append(Text("\nDocumentation:", style="bold"))
    for label, url in DOCS.get(doc_key, []):
        body.append(Text.from_markup(f"  📖 {label}\n     [link={url}][blue underline]{url}[/][/link]"))
    console.print()
    console.print(Panel(Group(*body), title=f"[bold magenta]DRY RUN · {title}", border_style="magenta", expand=True))
