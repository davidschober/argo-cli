import os
from pathlib import Path

# Rich reads COLUMNS when the console is created, so set it before importing argo_cli.
# A wide console keeps messages on one line, which keeps the string checks simple.
os.environ["COLUMNS"] = "200"

import pytest  # noqa: E402
from click.testing import CliRunner  # noqa: E402

from argo_cli import ui  # noqa: E402
from argo_cli.cli import cli  # noqa: E402

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(autouse=True)
def _restore_console():
    # `find --format druids` points ui.console at stderr; undo that between tests.
    original = ui.console
    yield
    ui.console = original


@pytest.fixture
def argo():
    """Run the CLI in-process with fake delays off. Returns click's Result."""
    runner = CliRunner()

    def run(*args, input=None):
        return runner.invoke(cli, ["--fast", *map(str, args)], input=input, prog_name="argo")

    return run
