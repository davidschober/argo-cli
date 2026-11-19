"""argo accession: accession registered druids through Preassembly.

Follows SDR User Guide > Accessioning > Preassembly: stage one folder per
druid, write a manifest.csv (druid,object), fill in the webform, run a
discovery report, then the Preassembly run.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import click
from rich.syntax import Syntax
from rich.table import Table

from ..file_manifest import load_and_validate, resource_tree
from ..ui import collect_druids, console, fake_progress, fake_steps, would_have

CONTENT_TYPES = ["image", "book", "document", "file", "geo", "media", "3d", "map", "webarchive-seed"]
OCR_TYPES = {"image", "book", "document"}
DEFAULT_LANGS = ["English", "French", "Spanish", "German", "Russian"]
UNSUPPORTED_LANGS = {"arabic", "chinese", "hebrew", "japanese", "korean", "persian"}
PROJECT_RE = re.compile(r"^[A-Za-z0-9_-]+$")
OCR_BATCH_ITEMS = 500  # above this, the guide says to contact the SDR team first


def _read_targets(targets: tuple[str, ...]) -> list[tuple[str, str]]:
    """Return (bare druid, folder) pairs. A CSV may have an 'object' column for non-druid folder names."""
    if len(targets) == 1 and Path(targets[0]).suffix.lower() == ".csv" and Path(targets[0]).is_file():
        with open(targets[0], newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if "object" in (reader.fieldnames or []):
                rows = list(reader)
                druids = collect_druids(tuple(r["druid"] for r in rows))
                return [(d.removeprefix("druid:"), r["object"]) for d, r in zip(druids, rows)]
    return [(d.removeprefix("druid:"), d.removeprefix("druid:")) for d in collect_druids(targets)]


@click.command()
@click.argument("targets", nargs=-1, required=True)
@click.option("--project-name", required=True, help="Unique per user; only A-Z a-z 0-9 - _ (no spaces).")
@click.option("--content-type", type=click.Choice(CONTENT_TYPES), required=True,
              help="Must match the content type the druids were registered with.")
@click.option("--staging", required=True,
              help="Staging location: /{storageMount}/path on an approved mount, or a Globus link.")
@click.option("--file-manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="file_manifest.csv for complex content: labels, order, roles, purl vs preservation-only. "
                   "Required for media.")
@click.option("--ocr", is_flag=True, help="Auto-generate OCR (image, book, document only).")
@click.option("--have-ocr", is_flag=True, help="ALTO XML files are already staged next to the images.")
@click.option("--lang", "languages", multiple=True, help="OCR language, up to 8. Default: " + ", ".join(DEFAULT_LANGS))
@click.option("--pss", type=click.Choice(["default", "all"]), default="default", show_default=True,
              help="Preserve/shelve/publish: 'default' publishes access files only; 'all' publishes everything.")
@click.option("--discovery-only", is_flag=True, help="Stop after the discovery report.")
def accession(targets, project_name, content_type, staging, file_manifest, ocr, have_ocr, languages, pss, discovery_only):
    """Accession content for registered druids using Preassembly.

    TARGETS are druids, a .txt with one druid per line, or a .csv with a
    'druid' column. A CSV with 'druid,object' columns is used as the
    manifest, so folders don't have to be named after druids (unless
    you use a file manifest).

    \b
    Examples:
      # simple book batch with OCR
      argo accession examples/accession.csv --project-name rumsey_batch_7 \\
          --content-type book --staging /dor/staging/rumsey/batch7 --ocr --lang English

    \b
      # complex media: file manifest controls resources, labels, order, purl vs preservation
      argo accession examples/accession_with_file_manifest.csv --project-name oral_hist_2026 \\
          --content-type media --staging /dor/staging/oralhist \\
          --file-manifest examples/file_manifest.csv
    """
    # Webform rules, checked up front.
    problems = []
    if not PROJECT_RE.match(project_name):
        problems.append("--project-name may only contain A-Z, a-z, 0-9, hyphen and underscore")
    if not (staging.startswith("/") or "globus" in staging):
        problems.append("--staging must be /{storageMount}/... on an approved content mount, or a Globus link")
    if content_type == "media" and not file_manifest:
        problems.append("media content always needs a file manifest (--file-manifest file_manifest.csv)")
    if file_manifest and pss != "default":
        problems.append("with a file manifest, leave preserve/shelve/publish as default (the manifest decides per file)")
    if ocr and content_type not in OCR_TYPES:
        problems.append(f"OCR isn't offered for {content_type} (only image, book, document)")
    if ocr and have_ocr:
        problems.append("--ocr and --have-ocr are mutually exclusive")
    if len(languages) > 8:
        problems.append("choose at most 8 OCR languages")
    bad_langs = [lang for lang in languages if lang.lower() in UNSUPPORTED_LANGS]
    if bad_langs:
        problems.append(f"OCR doesn't yet support {', '.join(bad_langs)} (contact the SDR team)")
    if problems:
        raise click.UsageError("\n  ".join(["Preassembly webform would reject this:"] + problems))

    pairs = _read_targets(targets)
    fm = None
    if file_manifest:
        renamed = [(d, o) for d, o in pairs if d != o]
        if renamed:
            raise click.UsageError(f"with a file manifest, folders must be named after druids; "
                                   f"'{renamed[0][1]}' is used for {renamed[0][0]}")
        fm = load_and_validate(file_manifest, [d for d, _ in pairs])
    console.rule(f"[bold]argo accession[/] · {project_name} · {len(pairs)} object(s) · {content_type}")

    manifest = "druid,object\n" + "\n".join(f"{d},{o}" for d, o in pairs)
    console.print("[bold]manifest.csv[/] (would be written to the staging root):")
    console.print(Syntax(manifest if len(pairs) <= 8 else "\n".join(manifest.splitlines()[:9]) + "\n…", "text",
                         theme="ansi_dark", line_numbers=False))

    if fm:
        console.print()
        console.print(resource_tree(fm))
        for w in fm.warnings:
            console.print(f"  [yellow]⚠ {w}[/]")
        if fm.errors:
            console.print(f"\n[bold red]✗ file_manifest.csv has {len(fm.errors)} problem(s); "
                          f"the discovery report would fail:[/]")
            for e in fm.errors:
                console.print(f"  [red]•[/] {e}")
            raise SystemExit(1)
        console.print("[bold green]✓ file_manifest.csv passes local checks[/]\n")

    fake_steps([
        f"Resolving staging location {staging}",
        "Checking manifest.csv: header, no blank lines, no repeated druids",
        "Checking each druid is registered with content type " + content_type,
        "Matching manifest rows to staged folders",
    ] + (["Checking every staged file is listed in file_manifest.csv (and vice versa)",
          "Verifying any .md5 sidecar checksums"] if fm else []))
    console.print("\n[bold]Discovery report[/]")
    fake_progress("Discovery report", [d for d, _ in pairs], per_item=(0.05, 0.2))

    t = Table(header_style="bold")
    t.add_column("Druid", no_wrap=True)
    t.add_column("Folder")
    t.add_column("Discovery")
    for d, o in pairs:
        t.add_row(d, f"{staging.rstrip('/')}/{o}", "[green]no errors[/]")
    console.print(t)

    if not discovery_only:
        fake_progress("Preassembly run", [d for d, _ in pairs], per_item=(0.1, 0.4))

    langs = list(languages) or DEFAULT_LANGS
    actions = [
        f"Filled in the Preassembly webform: project [cyan]{project_name}[/], content type [bold]{content_type}[/], "
        f"staging [cyan]{staging}[/], file manifest: {'yes' if fm else 'no'}, "
        f"preserve/shelve/publish: {pss}.",
        "Ran a [bold]Discovery Report[/] job to catch problems (missing folders, bad filenames, druids not registered) "
        "before anything is sent to SDR.",
    ]
    if not discovery_only:
        actions.append("Once the report was clean, started the [bold]Preassembly run[/] from the report page. "
                       "It copies files, builds structural metadata, makes JP2 derivatives for images, "
                       "and starts accessionWF for each druid.")
    if ocr:
        actions.append(f"Requested OCR during accessioning in: [cyan]{', '.join(langs)}[/].")
    if fm:
        n_res = len({(r["druid"], r["sequence"]) for r in fm.rows})
        n_dark = sum(r["publish"].lower() == "no" for r in fm.rows)
        actions.append(f"{'Checked' if discovery_only else 'Built'} structural metadata from [cyan]{file_manifest.name}[/]: {len(fm.rows)} files in "
                          f"{n_res} labeled resources, in manifest order. {n_dark} file(s) go to preservation only "
                          "and stay off the Purl. Roles (thumbnail, caption, transcription) are set per file.")
    if have_ocr:
        actions.append("Attached the staged ALTO XML files as transcriptions (one per image, matching filenames).")
    actions.append("Sent you an email when each job finished. Large jobs (TBs) can take days.")

    notes = ["After accessioning, use Argo to enrich metadata and release items to SearchWorks/EarthWorks."]
    if ocr and len(pairs) > OCR_BATCH_ITEMS:
        notes.append(f"[yellow]OCR batch of {len(pairs)} items: the guide asks you to contact the SDR team "
                     f"for batches over {OCR_BATCH_ITEMS} items or 300 GB.[/]")
    if ocr and content_type == "document":
        notes.append("PDF OCR is searchable with the browser's Ctrl/Cmd+F, not the viewer's search-within.")
    if pss == "all":
        notes.append("[yellow]'all' publishes every file on the Purl. Check with the SDR team if unsure.[/]")

    would_have("accession.file-manifest" if fm else "accession", "Accessioning (Preassembly)", actions, notes=notes)
