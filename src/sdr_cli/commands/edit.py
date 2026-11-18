"""sdr edit <thing>: bulk edits, each mapped to an Argo bulk action.

Since October 2025, edit bulk actions open new versions automatically and
(for most actions) can close them afterwards. --keep-open covers the cases
where you want to make several edits before one accession.
"""

from __future__ import annotations

from pathlib import Path

import click

from ..ui import collect_druids, console, fake_progress, fake_steps, would_have

OCR_DEFAULT_LANGS = ["English", "French", "Spanish", "German", "Russian"]
OCR_UNSUPPORTED = {"arabic", "chinese", "hebrew", "japanese", "korean", "persian"}
OCR_MAX_DRUIDS = 100  # guide: no more than 100 druids / 500 GB per OCR bulk action


def _start(name: str, targets: tuple[str, ...]) -> list[str]:
    druids = collect_druids(targets)
    console.rule(f"[bold]sdr edit {name}[/] · {len(druids)} object(s)")
    return druids


def _version_step(keep_open: bool) -> str:
    if keep_open:
        return "Opened a new version on each object and [bold]left it open[/] (run Close version later to accession)."
    return ("Opened a new version on each object automatically, made the change, then closed it. "
            "Closing re-runs accessionWF, which updates the Purl and preservation copy.")


keep_open_opt = click.option("--keep-open", is_flag=True,
                             help="Don't close versions afterwards (to batch several edits into one accession).")


@click.group()
def edit():
    """Bulk-edit existing SDR objects. Each subcommand maps to an Argo bulk action.

    TARGETS can be druids, .txt or .csv files of druids, or '-' for stdin.
    """


@edit.command()
@click.argument("targets", nargs=-1, required=True)
@click.option("--lang", "languages", multiple=True,
              help="OCR language, repeatable. Default: " + ", ".join(OCR_DEFAULT_LANGS) + ". One or two works best.")
def ocr(targets, languages):
    """Run OCR (text extraction) on accessioned image or book items.

    \b
    Example:  sdr edit ocr druids.txt --lang English
    """
    bad = [lang for lang in languages if lang.lower() in OCR_UNSUPPORTED]
    if bad:
        raise click.UsageError(f"OCR supports Latin and Cyrillic scripts only; not {', '.join(bad)}")
    druids = _start("ocr", targets)
    langs = list(languages) or OCR_DEFAULT_LANGS
    if len(druids) > OCR_MAX_DRUIDS:
        console.print(f"[yellow]⚠ {len(druids)} druids: the guide asks for no more than {OCR_MAX_DRUIDS} druids "
                      f"(and 500 GB) per OCR bulk action. A real run would split this into "
                      f"{-(-len(druids) // OCR_MAX_DRUIDS)} batches.[/]")
    fake_steps([
        "Checking content type is image or book (document is experimental; map/file/geo not supported)",
        "Checking for existing third-party ALTO (never overwritten)",
        "Checking download rights (download-restricted items are skipped)",
    ], delay=(0.2, 0.5))
    fake_progress("Queuing ocrWF", druids)
    would_have(
        "edit.ocr",
        "OCR / Text extraction",
        [
            "Submitted the [bold]Text extraction[/] bulk action (Perform actions → Modify objects).",
            f"For each eligible object, queued ABBYY FineReader OCR in [cyan]{', '.join(langs)}[/]. The queue is "
            "shared with Goobi and Preassembly OCR, so a job takes anywhere from minutes to a day.",
            "Produced ALTO XML (role: transcription), one plain-text file, and an item-level searchable PDF. "
            "The original images are not changed.",
            "Opened and closed a new version automatically (OCR always closes versions).",
        ],
        notes=[
            "If item rights are no-download, the ALTO files inherit that and search-within won't work. "
            "Fix with file-level rights in the structural metadata CSV.",
            "Images over 30,000 px on the long side are skipped.",
            "Don't restart failed OCR from the workflow grid. Ask in #dlss-aaas.",
            "Check batch size first: Argo search results → Profile View → 'Preserved file size'.",
        ],
    )


VIEW = ["world", "stanford", "location-based", "citation-only", "dark"]
DOWNLOAD = ["world", "stanford", "location-based", "none"]
LOCATIONS = ["spec", "music", "ars", "art", "hoover", "m&m"]


@edit.command()
@click.argument("targets", nargs=-1, required=True)
@click.option("--view", type=click.Choice(VIEW), required=True)
@click.option("--download", type=click.Choice(DOWNLOAD), default="none", show_default=True)
@click.option("--location", type=click.Choice(LOCATIONS), help="Required when view or download is location-based.")
@click.option("--cdl", is_flag=True, help="Controlled digital lending (only with --view stanford --download none).")
@keep_open_opt
def rights(targets, view, download, location, cdl, keep_open):
    """Change object view/download rights (Update rights bulk action)."""
    if "location-based" in (view, download) and not location:
        raise click.UsageError("--location is required for location-based rights")
    if cdl and not (view == "stanford" and download == "none"):
        raise click.UsageError("--cdl only works with --view stanford --download none")
    if view in ("dark", "citation-only"):
        download = "none"
    druids = _start("rights", targets)
    fake_progress("Updating rights", druids)
    would_have(
        "edit.rights",
        "Update rights",
        [
            "Submitted the [bold]Update rights[/] bulk action (Manage rights and administrative metadata).",
            f"Set view=[cyan]{view}[/], download=[cyan]{download}[/]"
            + (f", location=[cyan]{location}[/]" if location else "") + (", CDL on" if cdl else "") + ".",
            _version_step(keep_open),
        ],
        notes=["[yellow]This overwrites every file's rights, including file-specific settings "
               "such as public ALTO on no-download items.[/]"],
    )


@edit.command()
@click.argument("targets", nargs=-1, required=True)
@click.option("--to", "collection", required=True, help="Collection druid.")
@keep_open_opt
def collection(targets, collection, keep_open):
    """Move objects to a different collection (Update collection bulk action)."""
    druids = _start("collection", targets)
    fake_progress("Updating collection", druids)
    would_have(
        "edit.collection",
        "Update collection",
        [
            "Submitted the [bold]Update collection[/] bulk action (Manage structural metadata).",
            f"Set each object's collection to [cyan]{collection}[/]. Unlike tags, collections are visible in "
            "SearchWorks and on the Purl.",
            _version_step(keep_open),
        ],
    )


@edit.command()
@click.argument("tags_csv", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def tags(tags_csv):
    """Replace tags from a CSV: druid,tag,tag,... (Import tags bulk action).

    \b
    Example row:  druid:bc123df4567,Project : Maps,Format : Atlas
    """
    rows = [ln for ln in tags_csv.read_text().splitlines() if ln.strip()]
    console.rule(f"[bold]sdr edit tags[/] · {len(rows)} row(s)")
    fake_progress("Importing tags", [r.split(",")[0] for r in rows])
    would_have(
        "edit.tags",
        "Import tags",
        [
            "Submitted the [bold]Import tags[/] bulk action (Tags and Reporting) with this CSV.",
            "Replaced each listed druid's tags with the tags in its row. Tags use 'Term : Subterm'.",
            "Tags are administrative only, so no new version is opened and nothing is re-accessioned.",
        ],
        notes=["Use Argo's [bold]Export tags[/] first to start from the current tags."],
    )


CONTENT_TYPES = ["book", "document", "file", "geo", "image", "map", "media", "3d", "webarchive-seed"]


@edit.command("content-type")
@click.argument("targets", nargs=-1, required=True)
@click.option("--from", "current", type=click.Choice(CONTENT_TYPES), help="Only change objects of this type.")
@click.option("--to", "new", type=click.Choice(CONTENT_TYPES), required=True)
@click.option("--reading-order", type=click.Choice(["left-to-right", "right-to-left"]))
@keep_open_opt
def content_type(targets, current, new, reading_order, keep_open):
    """Change content and resource type (Update content type bulk action)."""
    druids = _start("content-type", targets)
    fake_progress("Updating content type", druids)
    would_have(
        "edit.content-type",
        "Update content type",
        [
            "Submitted the [bold]Update content type[/] bulk action (Manage structural metadata).",
            f"Changed content type {('from ' + current + ' ') if current else ''}to [cyan]{new}[/]"
            + (f" with reading order {reading_order}" if reading_order else "")
            + " and updated resource types to match. This changes how the Purl viewer shows the item.",
            _version_step(keep_open),
        ],
        notes=["Media self-deposits need this after accessioning, and the files must be streamable (MP3/MP4)."]
        if new == "media" else None,
    )


@edit.command()
@click.argument("targets", nargs=-1)
@click.option("--export", "export_path", type=click.Path(path_type=Path), help="Download a spreadsheet for TARGETS.")
@click.option("--validate", "validate_path", type=click.Path(exists=True, path_type=Path),
              help="Check an edited spreadsheet against Cocina without changing anything.")
@click.option("--import", "import_path", type=click.Path(exists=True, path_type=Path), help="Apply an edited spreadsheet.")
@keep_open_opt
def descriptive(targets, export_path, validate_path, import_path, keep_open):
    """Round-trip descriptive metadata through a spreadsheet.

    \b
    sdr edit descriptive druids.txt --export desc.csv   # edit in Excel…
    sdr edit descriptive --validate desc.csv
    sdr edit descriptive --import desc.csv
    """
    if sum(bool(x) for x in (export_path, validate_path, import_path)) != 1:
        raise click.UsageError("choose exactly one of --export, --validate, --import")
    if export_path:
        druids = _start("descriptive --export", targets)
        fake_progress("Exporting descriptive metadata", druids)
        actions = [
            "Submitted [bold]Download descriptive metadata spreadsheet[/] (Manage descriptive metadata).",
            f"Saved one row per object, with Cocina description flattened to columns, to [cyan]{export_path}[/].",
        ]
    elif validate_path:
        console.rule("[bold]sdr edit descriptive --validate[/]")
        fake_steps(["Reading spreadsheet", "Validating each row against Cocina"])
        actions = [
            "Submitted [bold]Validate descriptive metadata spreadsheet[/].",
            f"Reported any row in [cyan]{validate_path}[/] that would produce invalid Cocina. No objects changed.",
        ]
    else:
        console.rule("[bold]sdr edit descriptive --import[/]")
        fake_steps(["Reading spreadsheet", "Validating against Cocina", "Diffing against current metadata"])
        actions = [
            "Submitted [bold]Upload descriptive metadata spreadsheet[/].",
            f"Wrote the new description from [cyan]{import_path}[/] for each changed row.",
            _version_step(keep_open),
        ]
    would_have("edit.descriptive", "Descriptive metadata", actions,
               notes=["Items with FOLIO-sourced metadata should be edited in FOLIO, then use "
                      "'Refresh metadata from FOLIO record'."])
