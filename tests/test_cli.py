"""Smoke tests: every command runs, every example file does what the README says."""

import re

import pytest

from argo_cli.ui import normalize_druid

from conftest import EXAMPLES

DRUID_LINE = re.compile(r"^druid:[b-df-hjkmnp-tv-z]{2}\d{3}[b-df-hjkmnp-tv-z]{2}\d{4}$")


# --- the basics -------------------------------------------------------------

def test_version(argo):
    r = argo("--version")
    assert r.exit_code == 0
    assert r.output.startswith("argo, version")


@pytest.mark.parametrize("cmd", [
    [], ["register"], ["accession"], ["edit"], ["edit", "ocr"], ["edit", "rights"],
    ["edit", "collection"], ["edit", "tags"], ["edit", "content-type"], ["edit", "descriptive"],
    ["find"], ["status"],
])
def test_help_uses_argo_name(argo, cmd):
    r = argo(*cmd, "--help")
    assert r.exit_code == 0
    assert "sdr " not in r.output  # the old command name; "SDR" the repository is fine


def test_every_command_is_dry_run(argo):
    r = argo("status", "bb111cc2222")
    assert "Nothing was sent to SDR" in r.output


# --- druid parsing ----------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("druid:bb111cc2222", ("druid:bb111cc2222", True)),
    ("bb111cc2222", ("druid:bb111cc2222", True)),
    ("  bb111cc2222 ", ("druid:bb111cc2222", True)),
    ("druid:ab123cd4567", ("druid:ab123cd4567", False)),  # vowels aren't allowed
    ("bb111cc222", ("bb111cc222", False)),               # too short
])
def test_normalize_druid(value, expected):
    assert normalize_druid(value) == expected


@pytest.mark.parametrize("source", ["druids.txt", "druids.csv"])
def test_druid_files(argo, source):
    r = argo("status", EXAMPLES / source)
    assert r.exit_code == 0
    assert "3 object(s)" in r.output
    assert "don't look like druids" not in r.output


def test_bad_druids_warn_but_run(argo):
    r = argo("status", EXAMPLES / "druids_with_errors.txt")
    assert r.exit_code == 0
    assert "3 value(s) don't look like druids" in r.output


def test_druids_from_stdin(argo):
    r = argo("edit", "ocr", "-", input="druid:bb111cc2222\ndd333ff4444\n")
    assert r.exit_code == 0
    assert "2 object(s)" in r.output


# --- register ---------------------------------------------------------------

def test_register_good(argo):
    r = argo("register", EXAMPLES / "register.csv", "--validate-only")
    assert r.exit_code == 0, r.output
    assert "All rows pass" in r.output


def test_register_minimal_with_flags(argo):
    f = EXAMPLES / "register_minimal.csv"
    assert argo("register", f, "--validate-only").exit_code == 1  # APO etc. missing without flags
    r = argo("register", f, "--validate-only", "--apo", "druid:hv992ry2431",
             "--workflow", "registrationWF", "--content-type", "image")
    assert r.exit_code == 0, r.output


def test_register_errors(argo):
    r = argo("register", EXAMPLES / "register_with_errors.csv", "--validate-only")
    assert r.exit_code == 1
    for msg in [
        "must be a prefixed druid",
        "initial_workflow is required",
        "did you mean 'image'?",
        "must follow the prefix:value pattern",
        "title is required",
        "rights_location is required",
        "must be colon-separated",
        "should not include the JIRA prefix",
        "appears more than once",
    ]:
        assert msg in r.output, msg


def test_register_full_run(argo):
    r = argo("register", EXAMPLES / "register.csv")
    assert r.exit_code == 0
    assert "DRY RUN" in r.output and "Pretend bulk action report" in r.output


# --- accession --------------------------------------------------------------

ACCESSION = ["--project-name", "test_batch", "--staging", "/dor/staging/test"]


def test_accession_simple(argo):
    r = argo("accession", EXAMPLES / "accession.csv", *ACCESSION, "--content-type", "book", "--ocr")
    assert r.exit_code == 0, r.output
    assert "Requested OCR" in r.output


def test_accession_renamed_folders(argo):
    r = argo("accession", EXAMPLES / "accession_renamed_folders.csv", *ACCESSION, "--content-type", "image")
    assert r.exit_code == 0, r.output
    assert "bb111cc2222,rumsey_atlas_plate_01" in r.output


@pytest.mark.parametrize("manifest, objects, content_type", [
    ("file_manifest.csv", "accession_with_file_manifest.csv", "media"),
    ("file_manifest_images_with_labels.csv", "accession_images_with_labels.csv", "image"),
])
def test_accession_file_manifest_good(argo, manifest, objects, content_type):
    r = argo("accession", EXAMPLES / objects, *ACCESSION, "--content-type", content_type,
             "--file-manifest", EXAMPLES / manifest)
    assert r.exit_code == 0, r.output
    assert "passes local checks" in r.output


def test_accession_file_manifest_errors(argo):
    r = argo("accession", EXAMPLES / "accession_with_file_manifest.csv", *ACCESSION,
             "--content-type", "media", "--file-manifest", EXAMPLES / "file_manifest_with_errors.csv")
    assert r.exit_code == 1
    assert "file_manifest.csv has 8 problem(s)" in r.output  # matches the README
    assert "role 'ocr' will be ignored" in r.output


def test_accession_file_manifest_rejects_renamed_folders(argo):
    r = argo("accession", EXAMPLES / "accession_renamed_folders.csv", *ACCESSION,
             "--content-type", "image", "--file-manifest", EXAMPLES / "file_manifest.csv")
    assert r.exit_code == 2
    assert "folders must be named after druids" in r.output


@pytest.mark.parametrize("extra, msg", [
    (["--content-type", "media"], "media content always needs a file manifest"),
    (["--content-type", "map", "--ocr"], "OCR isn't offered for map"),
    (["--content-type", "book", "--ocr", "--lang", "Arabic"], "OCR doesn't yet support Arabic"),
])
def test_accession_webform_rules(argo, extra, msg):
    r = argo("accession", EXAMPLES / "accession.csv", *ACCESSION, *extra)
    assert r.exit_code == 2
    assert msg in r.output


def test_accession_bad_project_name(argo):
    r = argo("accession", "bb111cc2222", "--project-name", "has spaces", "--staging", "/dor/x",
             "--content-type", "image")
    assert r.exit_code == 2
    assert "--project-name may only contain" in r.output


# --- edit -------------------------------------------------------------------

@pytest.mark.parametrize("args", [
    ["ocr", EXAMPLES / "druids.txt", "--lang", "English"],
    ["rights", EXAMPLES / "druids.txt", "--view", "world", "--download", "world"],
    ["rights", EXAMPLES / "druids.txt", "--view", "location-based", "--location", "spec"],
    ["collection", EXAMPLES / "druids.txt", "--to", "druid:bc778pm9866"],
    ["content-type", EXAMPLES / "druids.csv", "--to", "book", "--keep-open"],
    ["tags", EXAMPLES / "tags.csv"],
    ["descriptive", EXAMPLES / "druids.txt", "--export", "desc.csv"],
    ["descriptive", "--validate", EXAMPLES / "descriptive.csv"],
    ["descriptive", "--import", EXAMPLES / "descriptive.csv"],
])
def test_edit_commands(argo, args):
    r = argo("edit", *args)
    assert r.exit_code == 0, r.output
    assert "DRY RUN" in r.output


def test_edit_keep_open(argo):
    r = argo("edit", "rights", "bb111cc2222", "--view", "world", "--keep-open")
    assert "left it open" in r.output


@pytest.mark.parametrize("args, msg", [
    (["rights", "bb111cc2222", "--view", "location-based"], "--location is required"),
    (["rights", "bb111cc2222", "--view", "world", "--cdl"], "--cdl only works"),
    (["ocr", "bb111cc2222", "--lang", "Japanese"], "Latin and Cyrillic scripts only"),
    (["descriptive", "bb111cc2222"], "choose exactly one of"),
])
def test_edit_rejects(argo, args, msg):
    r = argo("edit", *args)
    assert r.exit_code == 2
    assert msg in r.output


# --- find / status ----------------------------------------------------------

def test_find_druids_format_is_pipeable(argo):
    r = argo("find", "--format", "druids", "--limit", "5")
    assert r.exit_code == 0
    lines = r.stdout.splitlines()
    assert len(lines) == 5
    assert all(DRUID_LINE.match(ln) for ln in lines), lines


def test_find_csv_format(argo):
    r = argo("find", "--format", "csv", "--limit", "2")
    assert r.stdout.splitlines()[0] == "druid,source_id,title,content_type,status"


def test_find_hrid_gets_prefix(argo):
    r = argo("find", "--hrid", "4647701")
    assert "a4647701" in r.output


def test_find_source_id_is_quoted(argo):
    r = argo("find", "--source-id", "sul:M1994_b033")
    assert '"sul:M1994_b033"' in r.output
