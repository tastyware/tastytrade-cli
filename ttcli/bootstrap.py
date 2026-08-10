import subprocess
import sys
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Annotated

from typer import Argument, Typer


def copy(src: Traversable, dest: Path) -> None:
    if src.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        for entry in src.iterdir():
            copy(entry, dest / entry.name)
    else:
        dest.write_bytes(src.read_bytes())
        print(f"Created directory {dest}")


def uv(args: list[str], cwd: Path | None = None) -> None:
    try:
        subprocess.run(["uv", *args], cwd=cwd, check=True)
    except FileNotFoundError:
        sys.exit("Error: uv not found! See https://docs.astral.sh/uv/#installation")
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)


cli = Typer(no_args_is_help=True)


@cli.command(
    name="bootstrap",
    no_args_is_help=True,
    help="Bootstrap a new project using the Tastytrade SDK.",
)
def bootstrap(name: Annotated[str, Argument(help="Name of the new project.")]) -> None:
    target = Path.cwd() / name
    if target.exists():
        sys.exit(f"Error: path {target} already exists!")
    uv(["init", "--bare", name])
    uv(["add", "streaq", "tastytrade", "pydantic-settings"], cwd=target)
    template = files("ttcli.data") / "project_template"
    copy(template, target)
    print(f"Project {name} bootstrapped successfully!")
