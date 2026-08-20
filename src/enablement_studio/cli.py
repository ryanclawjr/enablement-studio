from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from enablement_studio.models import Product
from enablement_studio.paths import DEMO_FILES, default_db_path, find_fixture
from enablement_studio.render import render_compare, render_output, render_run_list
from enablement_studio.runs import generate_and_save, output_from_run
from enablement_studio.serve import DEFAULT_HOST, DEFAULT_PORT, serve
from enablement_studio.store import Store

DEMO_PROJECT = "example"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="enablement",
        description="Local-first instructional design: Role → Enablement, Call → Coach, Lesson critic.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Run a packaged example (no API key).")
    demo.add_argument("product", choices=[item.value for item in Product])
    demo.add_argument("--json", action="store_true")
    demo.set_defaults(handler=_cmd_demo)

    for product in Product:
        command = sub.add_parser(product.value, help=f"Run {product.value} on a file or stdin.")
        command.add_argument("--file", type=Path)
        command.add_argument("--text")
        command.add_argument("--project", default="default")
        command.add_argument("--json", action="store_true")
        command.set_defaults(handler=_cmd_product, product=product)

    listed = sub.add_parser("list", help="List stored runs.")
    listed.add_argument("--project")
    listed.add_argument("--product", choices=[item.value for item in Product])
    listed.set_defaults(handler=_cmd_list)

    show = sub.add_parser("show", help="Print a stored run.")
    show.add_argument("run_id", type=int)
    show.add_argument("--json", action="store_true")
    show.set_defaults(handler=_cmd_show)

    compare = sub.add_parser("compare", help="Compare two stored runs.")
    compare.add_argument("left_id", type=int)
    compare.add_argument("right_id", type=int)
    compare.set_defaults(handler=_cmd_compare)

    served = sub.add_parser(
        "serve",
        help="Local web UI on loopback (default 127.0.0.1:8765).",
    )
    served.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Bind address (default 127.0.0.1, not 0.0.0.0).",
    )
    served.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Bind port (default 8765).",
    )
    served.set_defaults(handler=_cmd_serve)
    return parser


def _cmd_demo(args: argparse.Namespace) -> int:
    product = Product(args.product)
    path = find_fixture(DEMO_FILES[product.value])
    return _run_product(
        product,
        path.read_text(encoding="utf-8"),
        project=DEMO_PROJECT,
        as_json=args.json,
    )


def _cmd_product(args: argparse.Namespace) -> int:
    text = _read_input(args.file, args.text)
    return _run_product(args.product, text, project=args.project, as_json=args.json)


def _cmd_list(args: argparse.Namespace) -> int:
    product = Product(args.product) if args.product else None
    runs = Store(default_db_path()).list_runs(project=args.project, product=product)
    sys.stdout.write(render_run_list(runs))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    run = Store(default_db_path()).get_run(args.run_id)
    if args.json:
        print(json.dumps(run.artifacts.get("result", {}), indent=2))
        return 0
    output = output_from_run(run)
    sys.stdout.write(render_output(output, run))
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    store = Store(default_db_path())
    left = store.get_run(args.left_id)
    right = store.get_run(args.right_id)
    sys.stdout.write(render_compare(left, right))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        serve(host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 0
    return 0


def _run_product(product: Product, text: str, *, project: str, as_json: bool) -> int:
    output, _engine, run = generate_and_save(product, text, project=project)
    if as_json:
        print(json.dumps(output.to_dict(), indent=2))
        return 0
    sys.stdout.write(render_output(output, run))
    return 0


def _read_input(path: Path | None, text: str | None) -> str:
    if text:
        return text
    if path is None:
        raise ValueError("provide --file or --text")
    if str(path) == "-":
        return sys.stdin.read()
    return path.read_text(encoding="utf-8")
