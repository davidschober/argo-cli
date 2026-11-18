"""Entry point for the `sdr` command."""

import click

from .commands.accession import accession
from .commands.edit import edit
from .commands.find import find, status
from .commands.register import register


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--fast", is_flag=True, envvar="SDR_FAST", help="Skip the fake delays (also SDR_FAST=1).")
@click.version_option(package_name="sdr-cli")
@click.pass_context
def cli(ctx, fast):
    """sdr: a bulk power-user CLI for the Stanford Digital Repository (Argo).

    \b
    PROOF OF CONCEPT: no command contacts SDR. Each one checks its input,
    shows a pretend run, then explains what a real run would do and links
    to the documentation.

    \b
    Typical flow:
      sdr register items.csv --apo druid:hv992ry2431
      sdr accession registration_report.csv --ocr
      sdr status registration_report.csv
      sdr find --tag "Project : Maps" --format druids | sdr edit rights - --view world --download world
    """
    ctx.obj = {"fast": fast}


cli.add_command(register)
cli.add_command(accession)
cli.add_command(edit)
cli.add_command(find)
cli.add_command(status)
