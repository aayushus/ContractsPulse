#!/usr/bin/env python3
"""Change a ContractsPulse user's email and/or password.

Designed to run inside the `api` container where the app package and the
database connection are available, e.g.:

    docker compose exec api python scripts/change_credentials.py

Interactive by default. Flags / env vars allow non-interactive use:

    docker compose exec -T api python scripts/change_credentials.py \
        --email admin@admin.com --new-email me@example.com --new-password 'S3cret!'

Environment variable fallbacks: CURRENT_EMAIL, NEW_EMAIL, NEW_PASSWORD.
"""

import argparse
import getpass
import os
import sys

# Ensure the backend root (which contains the `app` package) is importable
# regardless of how the script is invoked.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def prompt_password() -> str:
    while True:
        pw = getpass.getpass("New password: ")
        if not pw:
            print("Password cannot be empty.")
            continue
        confirm = getpass.getpass("Confirm new password: ")
        if pw != confirm:
            print("Passwords do not match. Try again.\n")
            continue
        return pw


def main() -> int:
    parser = argparse.ArgumentParser(description="Change a ContractsPulse user's credentials.")
    parser.add_argument(
        "--email",
        default=os.environ.get("CURRENT_EMAIL", "admin@admin.com"),
        help="Email of the account to update (default: admin@admin.com).",
    )
    parser.add_argument(
        "--new-email",
        default=os.environ.get("NEW_EMAIL"),
        help="Optional new email for the account.",
    )
    parser.add_argument(
        "--new-password",
        default=os.environ.get("NEW_PASSWORD"),
        help="New password (omit to be prompted securely).",
    )
    args = parser.parse_args()

    target_email = (args.email or "").strip().lower()
    new_email = (args.new_email or "").strip().lower() or None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == target_email).first()
        if not user:
            print(f"Error: no user found with email '{target_email}'.", file=sys.stderr)
            return 1

        # Resolve the new password (prompt if not supplied).
        new_password = args.new_password
        if not new_password:
            if not sys.stdin.isatty():
                print(
                    "Error: --new-password (or NEW_PASSWORD) is required in non-interactive mode.",
                    file=sys.stderr,
                )
                return 2
            new_password = prompt_password()

        if new_email and new_email != user.email:
            clash = db.query(User).filter(User.email == new_email).first()
            if clash:
                print(f"Error: another account already uses '{new_email}'.", file=sys.stderr)
                return 3
            user.email = new_email

        user.hashed_password = hash_password(new_password)
        db.commit()

        print("Credentials updated successfully.")
        print(f"  Login email: {user.email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
