"""Command line: ``metbazarr build`` and ``metbazarr validate``."""

from __future__ import annotations

import argparse
import os
import sys


def _time_range(text: str | None, n: int) -> range:
    """Parse ``START:STOP`` (Python slice style, either end optional)."""
    if text is None:
        return range(n)
    start, _, stop = text.partition(":")
    return range(
        *slice(int(start) if start else None, int(stop) if stop else None).indices(n)
    )


def _array_block(n: int, block: int) -> range:
    """The block of times for this Slurm array task."""
    task = int(os.environ["SLURM_ARRAY_TASK_ID"])
    return range(task * block, min((task + 1) * block, n))


def cmd_build(args: argparse.Namespace) -> int:
    from metbazarr import build
    from metbazarr.recipe import load_recipe

    recipe = load_recipe(args.recipe)
    if args.step in ("plan",):
        p = build.plan(recipe)
        print(
            f"{recipe.domain.name}: {p.crop.ny} x {p.crop.nx} points, lat "
            f"{p.crop.latitudes[0]}..{p.crop.latitudes[-1]}, lon {p.crop.longitudes[0]}.."
            f"{p.crop.longitudes[-1]}; partitions {p.parts}; {len(p.times)} times "
            f"{p.times[0]} .. {p.times[-1]}; output {recipe.output}"
        )
        return 0
    if args.step in ("create", "all"):
        build.create(recipe, overwrite=args.overwrite)
    if args.step in ("fill", "all"):
        n = len(recipe.times(build.archive_from(recipe).interval_hours))
        if args.array_block:
            indices = _array_block(n, args.array_block)
        else:
            indices = _time_range(args.times, n)
        build.fill(recipe, indices, allow_commit_mismatch=args.allow_commit_mismatch)
    if args.step in ("finish", "all"):
        report = build.finish(
            recipe, full_scan=not args.quick, validation_input=args.validation_input
        )
        print(report.format())
        return 0 if report.ok else 1
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from metbazarr.formats import FORMATS

    if args.format not in FORMATS:
        print(
            f"unknown format {args.format!r}; known: {sorted(FORMATS)}", file=sys.stderr
        )
        return 2
    report = FORMATS[args.format].validate(
        args.store, full_scan=not args.quick, validation_input=args.validation_input
    )
    print(report.format())
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metbazarr", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build a store from a recipe")
    b.add_argument("recipe")
    b.add_argument(
        "--step",
        choices=("plan", "create", "fill", "finish", "all"),
        default="all",
        help="plan: show what the recipe resolves to; create: write the empty store; "
        "fill: convert times; finish: check and validate (default: all)",
    )
    b.add_argument("--times", help="time indices to fill, START:STOP (default: all)")
    b.add_argument(
        "--array-block",
        type=int,
        help="fill block number $SLURM_ARRAY_TASK_ID of this many times",
    )
    b.add_argument("--overwrite", action="store_true", help="replace an existing store")
    b.add_argument(
        "--quick", action="store_true", help="finish: skip the full value scan"
    )
    b.add_argument(
        "--validation-input",
        action="store_true",
        help="finish: apply the rules for GLIDE validation inputs",
    )
    b.add_argument(
        "--allow-commit-mismatch",
        action="store_true",
        help="fill a store created by a different commit (development only)",
    )
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("validate", help="validate a store against a format")
    v.add_argument("store")
    v.add_argument("--format", default="glide")
    v.add_argument("--quick", action="store_true", help="skip the full value scan")
    v.add_argument(
        "--validation-input",
        action="store_true",
        help="apply the rules for GLIDE validation inputs",
    )
    v.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
