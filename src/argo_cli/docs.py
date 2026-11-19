"""Documentation links shown after every command.

Page IDs come from the SDR User Guide space on Consul (Confluence for SUL).
Argo source links are secondary references for developers.
"""

CONSUL = "https://consul.stanford.edu"
ARGO_GH = "https://github.com/sul-dlss/argo/blob/main"


def sdr(page_id: int, title: str) -> tuple[str, str]:
    # Short form so URLs don't wrap in the terminal; Confluence redirects to the titled URL.
    return f"SDR: {title}", f"{CONSUL}/pages/viewpage.action?pageId={page_id}"


def argo(label: str, path: str) -> tuple[str, str]:
    return f"Argo source: {label}", f"{ARGO_GH}/{path}"


BULK_ACTIONS = sdr(1812791914, "List of Argo bulk actions")
VERSIONS = sdr(155585145, "Opening and closing object versions")

DOCS: dict[str, list[tuple[str, str]]] = {
    "register": [
        sdr(1785069828, "Registration"),
        sdr(162171344, "Registering items using a bulk action CSV"),
        sdr(136360516, "Registration form tags"),
        sdr(139654965, "Generating tracking sheets after registration"),
        argo("RegistrationCsvConverter", "app/services/registration_csv_converter.rb"),
    ],
    "accession": [
        sdr(159747286, "Options for accessioning content"),
        sdr(1812791974, "Staging content for Preassembly"),
        sdr(1812792167, "Creating the manifest CSV"),
        sdr(1812792052, "Filling out the Preassembly webform"),
        sdr(1812791983, "Running a discovery report and running Preassembly"),
        sdr(1813119428, "Typical Preassembly settings for common types of content"),
        sdr(139636526, "Content mount paths"),
        sdr(1812791952, "After accessioning"),
    ],
    "edit.ocr": [
        sdr(1785071120, "Running OCR on accessioned items"),
        sdr(159318236, "Enabling full-text search with OCR"),
        BULK_ACTIONS,
        argo("TextExtractionJob", "app/jobs/text_extraction_job.rb"),
    ],
    "edit.rights": [
        sdr(1638466489, "Changing an item's access rights"),
        BULK_ACTIONS,
        argo("SetRightsJob", "app/jobs/set_rights_job.rb"),
    ],
    "edit.collection": [
        sdr(156860462, "Changing an item's collection"),
        sdr(139638391, "Creating a new collection"),
        BULK_ACTIONS,
    ],
    "edit.tags": [
        sdr(158243118, "Tagging and remediating tags"),
        BULK_ACTIONS,
    ],
    "edit.content-type": [
        sdr(1785432604, "Editing content type and resource type"),
        BULK_ACTIONS,
    ],
    "edit.descriptive": [
        sdr(155585149, "Editing Cocina descriptive metadata in Argo"),
        BULK_ACTIONS,
    ],
    "find": [
        sdr(1785070767, "Searching and filtering in Argo"),
        sdr(140350155, "The Argo search results page"),
        sdr(1785430497, "Finding SDR content"),
    ],
    "status": [
        VERSIONS,
        sdr(1785070767, "Searching and filtering in Argo"),
        sdr(1812791952, "After accessioning"),
    ],
}

DOCS["accession.file-manifest"] = [
    sdr(1812791947, "Accessioning complex content using a file manifest"),
    sdr(1812791949, "Accessioning images with captions (labels)"),
] + DOCS["accession"]

# Shown in `argo edit --help` and appended to every edit panel.
EDIT_COMMON = [
    sdr(1638465944, "About Argo bulk actions"),
    VERSIONS,
]
for key in [k for k in DOCS if k.startswith("edit.")]:
    DOCS[key] += EDIT_COMMON
