# argo: a POC bulk CLI for SDR / Argo

A proof-of-concept command-line tool for Stanford Digital Repository power users, to support discussion.
It shows the intended commands and workflow, but **no command contacts SDR or Argo.** Each command:

1. checks its input against the rules in the [SDR User Guide](https://consul.stanford.edu/pages/viewpage.action?pageId=1785069828),
2. shows a pretend run with progress bars and result tables (druids are randomly generated),
3. explains what a real run would have done, which Argo bulk action or Preassembly step it maps to,
   and links to the relevant SDR User Guide pages.

## Try it with uvx (no install)

If you have [uv](https://docs.astral.sh/uv/getting-started/installation/), you can run the CLI straight from
GitHub. Nothing to clone, no virtualenv to set up:

```bash
uvx --from git+https://github.com/davidschober/argo-cli argo --help
uvx --from git+https://github.com/davidschober/argo-cli argo find --hrid 4647701
```

Always include `--from git+https://…`. A plain `uvx argo` would look for a different package on PyPI.

To get a plain `argo` command you can call from anywhere:

```bash
uv tool install git+https://github.com/davidschober/argo-cli
argo --help
uv tool upgrade argo-cli      # pick up new changes later
```

The sample input files live in `examples/` in this repo. To try commands with them, clone the repo,
or download the files you need.

## Quick start (from a clone)

```bash
git clone https://github.com/davidschober/argo-cli && cd argo-cli
uv sync
uv run argo --help
uv run argo register examples/register.csv
```

Add `--fast` or set `ARGO_FAST=1` to skip the fake delays.

Run the tests (about 55 smoke tests, under a second):

```bash
uv run pytest
```

## Commands

| Command | Maps to | SDR User Guide page |
|---|---|---|
| `argo register items.csv` | Bulk action: Register druids (via CSV) | Registering items using a bulk action CSV |
| `argo accession manifest.csv --project-name … --content-type … --staging …` | Preassembly webform → discovery report → Preassembly run | Filling out the Preassembly webform |
| `argo accession … --file-manifest file_manifest.csv` | Preassembly with a file manifest (complex content and media) | Accessioning complex content using a file manifest |
| `argo edit ocr <druids> --lang English` | Bulk action: Text extraction | Running OCR on accessioned items |
| `argo edit rights <druids> --view … --download …` | Bulk action: Update rights | Changing an item's access rights |
| `argo edit collection <druids> --to <druid>` | Bulk action: Update collection | Changing an item's collection |
| `argo edit content-type <druids> --to book` | Bulk action: Update content type | Editing content type and resource type |
| `argo edit tags tags.csv` | Bulk action: Import tags | Tagging and remediating tags |
| `argo edit descriptive --export / --validate / --import` | Bulk actions: Download / Validate / Upload descriptive metadata spreadsheet | Editing Cocina descriptive metadata |
| `argo find "query" [facets] --format druids` | Argo search and facets | Searching and filtering in Argo |
| `argo status <druids>` | Processing Status facet and workflow grid | Opening and closing object versions |

Wherever a command takes `<druids>`, you can pass:
- individual druids (the `druid:` prefix is optional),
- a `.txt` file with one druid per line,
- a `.csv` file with a `druid` column, or
- `-` to read druids from stdin.

That makes commands composable:

```bash
argo find --project "Piano rolls" --status accessioned --format druids | argo edit ocr - --lang English
argo find --source-id sul:M1994_b033 --format druids > box33.txt
argo edit rights box33.txt --view world --download world --keep-open
argo edit content-type box33.txt --to book       # second edit, versions still open
```

## What the CLI checks, per the SDR User Guide

**register** ([bulk CSV page](https://consul.stanford.edu/pages/viewpage.action?pageId=162171344))
- APO and collection must be *prefixed* druids (`druid:bb123cc4567`).
- `initial_workflow` is required (usually `registrationWF`; Goobi items use `goobiWF`).
- Controlled values are case sensitive (`Image` is rejected, with a "did you mean `image`?" hint).
- `reading_order` is optional and defaults to left-to-right.
- `source_id` must be `prefix:value` and unique within the file.
- `title` may be blank only when `folio_instance_hrid` is present; FOLIO's title wins when both are given.
- `tags` and `tickets` are repeatable columns. Tags must be `Term : Subterm`; project and ticket tags have
  their own columns; tickets drop the `JIRA` prefix.
- `--validate-only` exits 1 on any problem, so it can gate a script or CI job.

**accession** ([Preassembly webform page](https://consul.stanford.edu/pages/viewpage.action?pageId=1812792052))
- Generates and shows the `manifest.csv` (`druid,object`, bare druids). A `druid,object` input CSV supports
  folders that aren't named after druids.
- Project names: `A-Z a-z 0-9 - _` only.
- Staging must be `/{storageMount}/…` or a Globus link.
- Media requires `--file-manifest`.
- OCR is offered for image, book, and document only, up to 8 languages, Latin and Cyrillic scripts only.
  Batches over 500 items or 300 GB get a warning.
- Always runs a discovery report before the Preassembly run (`--discovery-only` stops after the report).

**accession with a file manifest** ([complex content page](https://consul.stanford.edu/pages/viewpage.action?pageId=1812791947))

For media (where it's required), 3D, web archives, or images with custom labels, pass
`--file-manifest file_manifest.csv`. The CLI prints a resource tree showing how files group into labeled
resources and which files go on the Purl versus preservation only. It also checks:
- `druid` is the first column, and all required columns are present
  (`druid, filename, resource_label, sequence, publish, shelve, preserve, resource_type`).
- `publish`, `shelve`, and `preserve` are yes/no, and `publish` equals `shelve`.
- Each druid's files are listed together; sequences start at 1 and climb with no gaps (1,1,2,3).
- Files in one resource share the same label and type.
- `role` is one of transcription, caption, thumbnail, annotations, derivative, master.
  Other values are ignored, so they get a warning.
- Captions are `.vtt`; `file_language` is a BCP-47 code; `.md5` checksum files aren't listed.
- Every druid in `manifest.csv` appears in the file manifest, and vice versa. Folders must be named after druids.
- Preserve/shelve/publish stays `default`, because the manifest decides per file.

```bash
argo accession examples/accession_with_file_manifest.csv --project-name oral_hist_2026 \
    --content-type media --staging /dor/staging/oralhist --file-manifest examples/file_manifest.csv
# examples/file_manifest_with_errors.csv shows 8 errors and 1 warning
```

**edit ocr** ([OCR page](https://consul.stanford.edu/pages/viewpage.action?pageId=1785071120))
- Default languages are English, French, Spanish, German, and Russian.
- Warns when there are more than 100 druids per bulk action and shows how many batches it would split into.
- Explains how no-download item rights block search-within on the OCR text.

**edit, in general**
- Since October 2025, bulk edits open and close versions automatically.
  `--keep-open` leaves versions open so you can stack several edits into one accession.

**find**
- Supports the documented facets: project, tag, ticket, collection, APO, content type, object type,
  processing status, released-to, and registration date range.
- Google Books are excluded by default.
- Partial source-ID search is auto-quoted (`sul:M1994_b033` finds the whole box).
- Numeric SearchWorks HRIDs get the `a` prefix Argo needs (`4647701` becomes `a4647701`).

## Layout

```
src/argo_cli/
  cli.py                 # click group and global --fast flag
  ui.py                  # progress bars, "would have" panel, druid parsing
  docs.py                # Consul page IDs and Argo source links (one place to update)
  file_manifest.py       # file_manifest.csv checks and resource tree preview
  commands/{register,accession,edit,find}.py
tests/test_cli.py        # smoke tests: every command and every example file
examples/                # sample inputs (see below)
```

## Example files

| File | Use with | Shows |
|---|---|---|
| `druids.txt`, `druids.csv` | any `<druids>` argument | a druid list as text (one per line) or as a CSV with a `druid` column |
| `druids_with_errors.txt` | any `<druids>` argument | the warning for values that don't look like druids |
| `register.csv` | `register` | a clean batch: repeated `tags` columns, FOLIO HRID instead of a title, location-based rights |
| `register_minimal.csv` | `register --apo … --workflow … --content-type …` | shared settings passed as flags instead of columns |
| `register_with_errors.csv` | `register --validate-only` | one row per common mistake |
| `accession.csv` | `accession` | a simple `druid,object` manifest |
| `accession_renamed_folders.csv` | `accession` | staged folders that aren't named after druids |
| `accession_with_file_manifest.csv` + `file_manifest.csv` | `accession --content-type media --file-manifest …` | video and audio with captions, a transcript, and preservation-only masters |
| `accession_images_with_labels.csv` + `file_manifest_images_with_labels.csv` | `accession --content-type image --file-manifest …` | images with custom labels and a preservation-only PDF |
| `file_manifest_with_errors.csv` | `accession … --file-manifest …` | 8 errors and 1 warning |
| `tags.csv` | `edit tags` | `druid,tag,tag,…` rows |
| `descriptive.csv` | `edit descriptive --validate / --import` | a small descriptive metadata spreadsheet |

## Open questions for discussion

- **Backend.** Would a real version call the Argo bulk-action endpoints, the Preassembly API, or
  dor-services-app/sdr-api directly? How would it authenticate (token, SUNet)?
- **Accessioning paths.** Preassembly is modeled here. Is there a use case for Goobi or the SDR API deposit
  flow from the CLI?
- **Job handling.** Bulk actions and Preassembly run in the background and email when done. Should the CLI
  return a job ID with `argo jobs watch <id>`, or block until finished?
- **Safety rails.** Should the CLI split OCR jobs into batches of 100 automatically, check controlled
  values against live APO and collection lists, and look for already-registered source IDs before
  registering (the guide asks users to check for duplicates)?
