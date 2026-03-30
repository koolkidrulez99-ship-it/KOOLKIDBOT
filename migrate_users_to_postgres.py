import argparse
import os
import sys

from auth_storage import (
    ensure_postgres_auth_tables,
    find_existing_sqlite_auth_db,
    migrate_sqlite_auth_to_postgres,
    normalize_database_url,
)


def main():
    parser = argparse.ArgumentParser(
        description="One-time, idempotent migration from local SQLite auth storage to Postgres."
    )
    parser.add_argument(
        "--sqlite-path",
        help="Optional path to the old SQLite auth DB. If omitted, the script checks SQLITE_DB_PATH, user.db, and users.db.",
    )
    args = parser.parse_args()

    database_url = normalize_database_url(os.environ.get("DATABASE_URL"))
    if not database_url:
        print("DATABASE_URL is not set. Export your Render Postgres connection string first.", file=sys.stderr)
        return 1

    sqlite_path = find_existing_sqlite_auth_db(explicit_path=args.sqlite_path, default_name="users.db")
    if not sqlite_path:
        print(
            "No SQLite auth DB was found. Checked --sqlite-path, SQLITE_DB_PATH, user.db, and users.db.",
            file=sys.stderr,
        )
        return 1

    # Ensure the Postgres auth tables exist before we import any old rows.
    ensure_postgres_auth_tables(database_url)
    counts = migrate_sqlite_auth_to_postgres(sqlite_path=sqlite_path, database_url=database_url)

    print("Postgres auth migration complete.")
    print(f"SQLite source: {counts['sqlite_path']}")
    print(f"Users inserted: {counts['users']}")
    print(f"Licenses inserted: {counts['licenses']}")
    print(f"Password resets inserted: {counts['password_resets']}")
    print("Safe to re-run: duplicates are ignored by ON CONFLICT guards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
