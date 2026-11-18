"""sdr register: bulk-register items from a CSV.

Mirrors the "Register druids (via CSV)" bulk action. See
SDR User Guide > Registration > Registering items using a bulk action CSV.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

import click
from rich.table import Table

from ..ui import DRUID_RE, console, fake_druid, fake_progress, fake_steps, would_have

# Controlled values. The guide says these are case sensitive.
CONTENT_TYPES = ["book", "document", "file", "geo", "image", "map", "media", "3d", "webarchive-binary", "webarchive-seed"]
READING_ORDERS = ["left-to-right", "right-to-left"]
VIEW = ["world", "stanford", "location-based", "citation-only", "dark"]
DOWNLOAD = ["world", "stanford", "location-based", "none"]
LOCATIONS = ["spec", "music", "ars", "art", "hoover", "m&m"]
COMMON_WORKFLOWS = ["registrationWF", "goobiWF"]
TAG_RE = re.compile(r".+( : .+)+")
FORM_LIMIT = 600  # above this the guide recommends the CSV bulk action over the form


def _prefixed_druid(value: str) -> bool:
    return value.startswith("druid:") and bool(DRUID_RE.match(value))


def _validate_row(row: dict, n: int, opts: dict, raw_row: list[str], headers: list[str]) -> list[str]:
    errs: list[str] = []
    get = lambda k: (opts.get(k) or row.get(k) or "").strip()  # noqa: E731

    apo = get("administrative_policy_object")
    if not apo:
        errs.append("administrative_policy_object is required (column or --apo)")
    elif not _prefixed_druid(apo):
        errs.append(f"APO '{apo}' must be a prefixed druid, e.g. druid:bb123cc4567")

    coll = get("collection")
    if coll and not _prefixed_druid(coll):
        errs.append(f"collection '{coll}' must be a prefixed druid")

    if not get("initial_workflow"):
        errs.append("initial_workflow is required (most items use registrationWF; pass --workflow registrationWF)")

    ct = get("content_type")
    if not ct:
        errs.append("content_type is required")
    elif ct not in CONTENT_TYPES:
        hint = f" (did you mean '{ct.lower()}'? values are case sensitive)" if ct.lower() in CONTENT_TYPES else ""
        errs.append(f"content_type '{ct}' is not one of {', '.join(CONTENT_TYPES)}{hint}")

    ro = get("reading_order")
    if ro and ro not in READING_ORDERS:
        errs.append(f"reading_order '{ro}' must be blank, left-to-right, or right-to-left")

    sid = get("source_id")
    if not sid:
        errs.append("source_id is required")
    elif not re.match(r"^[^:\s]+:.+$", sid):
        errs.append(f"source_id '{sid}' must follow the prefix:value pattern")

    if not get("title") and not get("folio_instance_hrid"):
        errs.append("title is required unless folio_instance_hrid is present")

    view, dl = get("rights_view"), get("rights_download")
    if view not in VIEW:
        errs.append(f"rights_view '{view}' is not one of {', '.join(VIEW)}")
    if dl not in DOWNLOAD:
        errs.append(f"rights_download '{dl}' is not one of {', '.join(DOWNLOAD)}")
    if "location-based" in (view, dl) and get("rights_location") not in LOCATIONS:
        errs.append(f"rights_location is required for location-based rights ({', '.join(LOCATIONS)})")

    # Repeating columns: tags and tickets.
    for h, v in zip(headers, raw_row):
        v = v.strip()
        if not v:
            continue
        if h == "tags" and not TAG_RE.match(v):
            errs.append(f"tag '{v}' must be colon-separated, e.g. 'Format : Map'")
        if h == "tags" and v.lower().startswith(("project :", "ticket :")):
            errs.append(f"tag '{v}' belongs in the project_name or tickets column")
        if h == "tickets" and v.upper().startswith("JIRA"):
            errs.append(f"ticket '{v}' should not include the JIRA prefix (e.g. SDRO-123)")

    return [f"line {n}: {e}" for e in errs]


@click.command()
@click.argument("csv_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--apo", help="Prefixed APO druid; fills in the administrative_policy_object column.")
@click.option("--collection", help="Prefixed collection druid; fills in the collection column.")
@click.option("--workflow", help=f"Initial workflow, e.g. {', '.join(COMMON_WORKFLOWS)}.")
@click.option("--content-type", type=click.Choice(CONTENT_TYPES), help="Fills in the content_type column.")
@click.option("--project", help="Project name (project tag).")
@click.option("--description", default=None, help="Bulk action description shown on Argo's Bulk Actions page.")
@click.option("--validate-only", is_flag=True, help="Only check the CSV; exits 1 on any problem.")
def register(csv_file, apo, collection, workflow, content_type, project, description, validate_only):
    """Register every row of CSV_FILE as a new SDR object.

    \b
    Required columns (values are case sensitive):
      administrative_policy_object  prefixed druid, e.g. druid:bb123cc4567
      initial_workflow              usually registrationWF
      content_type                  book, image, document, file, map, media, ...
      source_id                     prefix:value, unique
      title                         unless folio_instance_hrid is present
      rights_view, rights_download  (+ rights_location if location-based)
    Optional: collection, reading_order (defaults to left-to-right),
      folio_instance_hrid, barcode, project_name, tags (repeatable),
      tickets (repeatable, e.g. SDRO-123)

    Example:  sdr register examples/register.csv --apo druid:hv992ry2431
    """
    opts = {
        "administrative_policy_object": apo,
        "collection": collection,
        "initial_workflow": workflow,
        "content_type": content_type,
        "project_name": project,
    }

    with csv_file.open(newline="", encoding="utf-8-sig") as fh:
        raw = list(csv.reader(fh))
    if len(raw) < 2:
        raise click.ClickException(f"{csv_file} has no data rows")
    headers, data = raw[0], raw[1:]
    rows = [dict(zip(headers, r)) for r in data]  # repeating columns: last value wins here; checked separately

    console.rule(f"[bold]sdr register[/] · {csv_file.name} · {len(rows)} row(s)")
    fake_steps(["Parsing CSV", "Checking column headers", "Validating rows against registration rules",
                "Checking for duplicate source IDs"], delay=(0.2, 0.5))

    errors = [e for i, (r, rr) in enumerate(zip(rows, data), start=2) for e in _validate_row(r, i, opts, rr, headers)]
    dupes = [s for s, c in Counter(r.get("source_id", "") for r in rows).items() if s and c > 1]
    errors += [f"source_id '{s}' appears more than once; each source ID must be unique" for s in dupes]

    if errors:
        console.print(f"\n[bold red]✗ {len(errors)} validation problem(s):[/]")
        for e in errors:
            console.print(f"  [red]•[/] {e}")
    else:
        console.print("\n[bold green]✓ All rows pass local validation[/]")

    if validate_only:
        raise SystemExit(1 if errors else 0)

    fake_progress("Registering", [r.get("source_id", "?") for r in rows])

    table = Table(title="Pretend bulk action report", header_style="bold")
    table.add_column("Druid", no_wrap=True)
    for h in ("Source ID", "Label", "Content type", "View/Download"):
        table.add_column(h)
    for r in rows:
        g = lambda k: opts.get(k) or r.get(k, "")  # noqa: E731
        table.add_row(
            f"[green]{fake_druid()}[/]",
            r.get("source_id", ""),
            (r.get("title") or f"(from FOLIO {r.get('folio_instance_hrid', '')})")[:40],
            g("content_type"),
            f"{r.get('rights_view', '')}/{r.get('rights_download', '')}",
        )
    console.print(table)

    notes = [
        "Then stage files and run [bold]sdr accession[/] with the new druids (Preassembly needs registered druids).",
        "In a large batch, Argo's index may take a while before every new item shows as registered.",
    ]
    if len(rows) <= FORM_LIMIT:
        notes.append(f"{len(rows)} rows with identical settings could also use the registration form; "
                     f"the guide suggests the CSV method above ~{FORM_LIMIT} items or when settings vary by row.")
    if errors:
        notes.append("[red]Rows flagged above would fail. The job skips failed rows and keeps going.[/]")

    would_have(
        "register",
        "Registration",
        [
            f"Submitted [cyan]{csv_file.name}[/] to the [bold]Register druids (via CSV)[/] bulk action"
            + (f' with description "{description}"' if description else "") + ".",
            f"Minted {len(rows)} druid(s) in the background (no browser needed), each with minimal descriptive and "
            "administrative metadata, governed by "
            + (f"[cyan]{apo}[/]" if apo else "the APO in each row")
            + (f" and added to [cyan]{collection}[/]" if collection else "") + ".",
            "Started each row's initial_workflow (usually registrationWF, or goobiWF / web archive / GIS workflows).",
            "Took titles from FOLIO wherever folio_instance_hrid was given, overriding the CSV title.",
            "Applied project, tag, and ticket tags, plus 'Registered By : <sunetid>'.",
            "Posted a report (druid, source id, label) and a log file on the Bulk Actions page.",
        ],
        notes=notes,
    )
