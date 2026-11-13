"""Operator CLI.

python -m app.cli create-user --email ops@uni.edu --name "Ops" --role admin
python -m app.cli seed            # load the sample dataset
python -m app.cli allocate        # run allocation once
"""

from __future__ import annotations

import argparse
import getpass
import sys

from .allocation import allocate_and_persist
from .auth import ROLES
from .database import SessionLocal
from .seed import ensure_categories, seed_sample, upsert_user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user", help="create or update a user")
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="")
    create.add_argument("--role", choices=ROLES, default="viewer")
    create.add_argument("--password", help="omit to be prompted")

    sub.add_parser("seed", help="replace data with the sample dataset")
    sub.add_parser("allocate", help="run the allocation engine")

    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        ensure_categories(db)
        if args.command == "create-user":
            password = args.password or getpass.getpass("Password: ")
            if len(password) < 8:
                print("Password must be at least 8 characters.", file=sys.stderr)
                return 1
            user = upsert_user(db, args.email, args.name or args.email, password, args.role)
            print(f"User {user.email} ({user.role}) is ready.")
        elif args.command == "seed":
            seed_sample(db)
            print("Sample dataset loaded.")
        elif args.command == "allocate":
            results, run = allocate_and_persist(db, triggered_by="cli")
            print(f"Allocated {len(results)} of {run.total_students} students.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
