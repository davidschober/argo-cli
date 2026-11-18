"""sdr find / sdr status: locate content and check where it is in the pipeline.

Follows SDR User Guide > Finding SDR content > Searching and filtering in Argo.
"""

from __future__ import annotations

import random
import re

import click
from rich.table import Table

from .. import ui
from ..ui import collect_druids, fake_druid, fake_steps, would_have

# Processing Status facet values.
STATUSES = ["accessioned", "registered", "opened", "in-accessioning", "unknown"]
OBJECT_TYPES = ["item", "collection", "agreement", "virtual-object", "admin-policy"]
CONTENT_TYPES = ["3d", "book", "document", "file", "geo", "image", "map", "media", "webarchive-binary", "webarchive-seed"]
RELEASE_TARGETS = ["searchworks", "earthworks", "sitemap"]
SAMPLE_TITLES = [
    "Map of the San Francisco Peninsula, 1895", "The Otter raft, no. 12", "Bob Fitch photograph, box 33",
    "Hoover poster collection: item 451", "Oral history: Class of 1968", "Herbarium specimen sheet",
    "Atlas of California, plate 22", "Commencement program, 1924",
]


def _normalize_hrid(hrid: str) -> tuple[str, bool]:
    """SearchWorks shows numeric catalog keys; Argo needs an 'a' prefix on them."""
    if re.fullmatch(r"\d+", hrid):
        return f"a{hrid}", True
    return hrid, False


@click.command()
@click.argument("query", required=False, default="")
@click.option("--project", help="Project facet, e.g. 'Piano rolls'.")
@click.option("--tag", "tags", multiple=True, help="Tag facet, e.g. 'Format : Map'. Repeatable.")
@click.option("--ticket", help="Ticket facet, e.g. SDRO-123.")
@click.option("--collection", help="Collection druid.")
@click.option("--apo", help="Admin policy druid.")
@click.option("--content-type", type=click.Choice(CONTENT_TYPES))
@click.option("--object-type", type=click.Choice(OBJECT_TYPES))
@click.option("--status", type=click.Choice(STATUSES), help="Processing Status facet.")
@click.option("--released-to", type=click.Choice(RELEASE_TARGETS), help="Only items currently released here.")
@click.option("--registered-after", metavar="YYYY-MM-DD")
@click.option("--registered-before", metavar="YYYY-MM-DD")
@click.option("--source-id", help="Exact or partial source ID; partial values act as a prefix, e.g. sul:M1994_b033")
@click.option("--hrid", help="FOLIO instance HRID. Numeric SearchWorks IDs get the 'a' prefix added.")
@click.option("--include-google-books", is_flag=True, help="Include the ~3M Google Books items (excluded by default).")
@click.option("--limit", default=8, show_default=True)
@click.option("--format", "fmt", type=click.Choice(["table", "csv", "druids"]), default="table", show_default=True,
              help="'druids' prints bare druids to stdout for piping into other commands.")
def find(query, project, tags, ticket, collection, apo, content_type, object_type, status, released_to,
         registered_after, registered_before, source_id, hrid, include_google_books, limit, fmt):
    """Search SDR through Argo's index (metadata only, not OCR full text).

    \b
    Examples:
      sdr find "Map of the San Francisco Peninsula"
      sdr find --source-id sul:M1994_b033                 # everything in box 33
      sdr find --hrid 4647701                             # becomes a4647701
      sdr find --project "Piano rolls" --status registered --format druids > todo.txt
      sdr find --collection druid:bc778pm9866 --format druids | sdr edit ocr -
    """
    if fmt == "druids":  # keep stdout clean for piping
        ui.console = ui.Console(stderr=True)
    out = ui.console

    tips = []
    q_parts = [query] if query else []
    if source_id:
        q_parts.append(f'"{source_id}"')  # quotes are required for partial source ID searches
    if hrid:
        hrid, fixed = _normalize_hrid(hrid)
        q_parts.append(hrid)
        if fixed:
            tips.append(f"Added the 'a' prefix: SearchWorks shows numeric IDs, but Argo indexes them as {hrid}.")
    if query and " " in query and not query.startswith('"'):
        tips.append(f'For an exact title, quote it: sdr find \'"{query}"\'')

    facets = {
        "Project": project, "Tag": " AND ".join(tags) or None, "Ticket": ticket, "Collection": collection,
        "Admin Policy": apo, "Content Type": content_type, "Object Type": object_type,
        "Processing Status": status,
        f"Released to {released_to}": "currently released" if released_to else None,
        "Registered": f"{registered_after or '*'} → {registered_before or 'today'}"
        if (registered_after or registered_before) else None,
        "Exclude Google Books": None if include_google_books else "yes",
    }
    facets = {k: v for k, v in facets.items() if v}
    q = " ".join(q_parts) or "*"

    out.rule(f"[bold]sdr find[/] {q}")
    for k, v in facets.items():
        out.print(f"  [dim]facet[/] {k}: [cyan]{v}[/]")
    fake_steps(["Building Solr query", "Querying Argo index"], delay=(0.2, 0.5))

    results = [
        {
            "druid": fake_druid(),
            "title": random.choice(SAMPLE_TITLES),
            "type": content_type or random.choice(["image", "book", "map", "document"]),
            "status": status or random.choice(STATUSES[:3]),
            "source_id": (source_id + f"_f{random.randint(1, 40):02d}") if source_id else f"sul:{random.randint(1000, 9999)}",
        }
        for _ in range(limit)
    ]

    if fmt == "druids":
        for r in results:
            click.echo(r["druid"])
    elif fmt == "csv":
        click.echo("druid,source_id,title,content_type,status")
        for r in results:
            click.echo(f'{r["druid"]},{r["source_id"]},"{r["title"]}",{r["type"]},{r["status"]}')
    else:
        t = Table(title=f"[dim]{limit} FAKE result(s)[/]", header_style="bold")
        t.add_column("Druid", no_wrap=True)
        for h in ("Source ID", "Title", "Type", "Status"):
            t.add_column(h)
        for r in results:
            color = {"accessioned": "green", "unknown": "red"}.get(r["status"], "yellow")
            t.add_row(r["druid"], r["source_id"], r["title"], r["type"], f"[{color}]{r['status']}[/]")
        out.print(t)

    would_have(
        "find",
        "Find content",
        [
            f"Ran an Argo search for [cyan]{q}[/] with {len(facets)} facet filter(s). Argo indexes all metadata "
            "(titles, druids, source IDs, HRIDs, barcodes, tags), but not OCR or transcript text.",
            "Returned every page of matches, not just the first, so the output can feed bulk actions.",
        ],
        notes=tips + ["In the web UI: same search and facets, then Bulk Action from the results. "
                      "Use Profile View to see the total preserved file size."],
    )


WF_STEPS = ["start-accession", "technical-metadata", "shelve", "publish", "preservation-ingest", "end-accession"]


@click.command()
@click.argument("targets", nargs=-1, required=True)
def status(targets):
    """Show processing status, version, and accessionWF progress."""
    druids = collect_druids(targets)
    out = ui.console
    out.rule(f"[bold]sdr status[/] · {len(druids)} object(s)")
    t = Table(header_style="bold")
    t.add_column("Druid", no_wrap=True)
    t.add_column("Status")
    t.add_column("Version")
    t.add_column("accessionWF")
    for d in druids:
        done = random.randint(0, len(WF_STEPS))
        steps = " ".join("[green]●[/]" if i < done else "[dim]○[/]" for i in range(len(WF_STEPS)))
        st = "accessioned" if done == len(WF_STEPS) else ("registered" if done == 0 else "in-accessioning")
        label = "complete" if done == len(WF_STEPS) else WF_STEPS[done]
        t.add_row(d, st, f"v{random.randint(1, 4)}", f"{steps} [dim]{label}[/]")
    out.print(t)
    would_have(
        "status",
        "Status",
        [
            "Looked up each object's Processing Status (registered, opened, in accessioning, accessioned, unknown) "
            "and current version.",
            "Listed every accessionWF step (plus ocrWF etc. if present) with its status and any error message.",
        ],
        notes=["If a status looks wrong, the Reindex bulk action often fixes it.",
               "Objects stuck in 'opened' usually have a version someone forgot to close."],
    )
