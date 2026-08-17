#!/usr/bin/env python3
"""Syncs each package's page-config/page-config.json into a DBAL seed file.

DBAL's real seed loader (SeedLoaderAction, dbal/shared/seeds/database/*.json)
already reads a {entity, records, metadata} envelope and is proven working
(idempotent via bootstrap:true/skipIfExists) -- rather than teaching DBAL a
second format, this wraps each package's bare-array page-config.json in that
same envelope and writes one generated file per package into the dbal repo.

DBAL entities live under a tenant path segment (/{tenant}/{package}/{Entity})
independent of any tenantId field on the row itself; every other PageConfig
row seeded this session uses tenant "system" for both, so this does too --
not a new convention, matching what's already there.

Usage:
    python3 scripts/sync_page_configs.py [--dbal-repo PATH] [--dry-run]

Regenerate whenever a package's page-config.json changes; this is meant to
be re-run, not maintained by hand (see CI wiring, still to land).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGES_ROOT = Path(__file__).resolve().parent.parent
# Not dbal/shared/... -- the dbal repo's real content lives under
# libraries/dbal/shared/... (libraries/ is its own top-level dir there, not
# a nested copy of this repo's naming). Confirmed against a live checkout
# rather than assumed; see metabuilder's CLAUDE.md for other repos that got
# this exact class of path wrong.
DEFAULT_DBAL_SEED_DIR = PACKAGES_ROOT.parent / "dbal" / "libraries" / "dbal" / "shared" / "seeds" / "database"
TENANT_ID = "system"


def load_page_config(package_dir: Path) -> list[dict] | None:
    page_config_path = package_dir / "page-config" / "page-config.json"
    if not page_config_path.is_file():
        return None
    with page_config_path.open() as f:
        records = json.load(f)
    if not isinstance(records, list):
        raise ValueError(f"{page_config_path}: expected a JSON array, got {type(records).__name__}")
    return records


def to_seed_record(row: dict, package_id: str) -> dict:
    """Fills in exactly the fields DBAL's PageConfig schema requires that a
    bare packages/*/page-config.json row doesn't already carry (sortOrder,
    isPublished are usually already present -- this is a safety net, not the
    primary source, so an already-correct row passes through unchanged
    except for tenantId)."""
    record = dict(row)
    record.setdefault("sortOrder", 0)
    record.setdefault("isPublished", True)
    record.setdefault("requiresAuth", True)
    record["tenantId"] = TENANT_ID
    if "packageId" not in record:
        record["packageId"] = package_id
    return record


def build_seed(package_id: str, rows: list[dict]) -> dict:
    return {
        "entity": "PageConfig",
        "version": "1.0",
        "description": f"Page routes for the {package_id} system package (synced from packages/{package_id}/page-config/page-config.json -- regenerate via scripts/sync_page_configs.py, don't hand-edit)",
        "records": [to_seed_record(row, package_id) for row in rows],
        "metadata": {
            "bootstrap": True,
            "skipIfExists": True,
            "timestampField": "createdAt",
            "useCurrentTimestamp": True,
        },
    }


def write_seed(package_id: str, seed: dict, dbal_seed_dir: Path, dry_run: bool) -> None:
    out_path = dbal_seed_dir / f"page_config_{package_id}.json"
    count = len(seed["records"])
    if dry_run:
        print(f"[dry-run] would write {out_path} ({count} records)")
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(seed, f, indent=2)
        f.write("\n")
    print(f"wrote {out_path} ({count} records)")


def find_collisions(packages: dict[str, list[dict]]) -> dict[str, list[tuple[str, str]]]:
    path_owners: dict[str, list[tuple[str, str]]] = {}
    for package_id, rows in packages.items():
        for row in rows:
            owners = path_owners.setdefault(row["path"], [])
            owners.append((package_id, row.get("id", "<no id>")))
    return {path: owners for path, owners in path_owners.items() if len(owners) > 1}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbal-repo", type=Path, default=None,
                         help="Path to the dbal repo checkout (default: sibling ../dbal)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dbal_seed_dir = (
        (args.dbal_repo / "libraries" / "dbal" / "shared" / "seeds" / "database")
        if args.dbal_repo is not None
        else DEFAULT_DBAL_SEED_DIR
    )
    if not args.dry_run and not dbal_seed_dir.is_dir():
        print(f"error: {dbal_seed_dir} does not exist", file=sys.stderr)
        return 1

    # Load every package's rows before writing anything. PageConfig.path has
    # a unique index in DBAL; two packages claiming the same path would seed
    # fine individually but fail (or silently clobber) only once both land
    # together, far from either package's own file. Collecting everything
    # first is the only point that can see both sides of that at once.
    packages: dict[str, list[dict]] = {}
    for package_dir in sorted(PACKAGES_ROOT.iterdir()):
        if not package_dir.is_dir() or package_dir.name.startswith("."):
            continue
        rows = load_page_config(package_dir)
        if rows:
            packages[package_dir.name] = rows

    collisions = find_collisions(packages)
    if collisions:
        print("error: the following paths are claimed by more than one package:", file=sys.stderr)
        for path, owners in sorted(collisions.items()):
            owner_desc = ", ".join(f"{pkg}:{rec_id}" for pkg, rec_id in owners)
            print(f"  {path} -> {owner_desc}", file=sys.stderr)
        print(
            "\nFix the source packages' page-config.json files so each path has one "
            "owner, then re-run -- this script will not silently pick a winner.",
            file=sys.stderr,
        )
        return 1

    total_packages = 0
    total_records = 0
    for package_id, rows in packages.items():
        seed = build_seed(package_id, rows)
        write_seed(package_id, seed, dbal_seed_dir, args.dry_run)
        total_packages += 1
        total_records += len(rows)

    print(f"\n{total_packages} package(s), {total_records} PageConfig record(s) total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
