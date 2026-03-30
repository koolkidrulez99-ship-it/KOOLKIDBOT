import argparse
import os
import sys

from auth_storage import normalize_database_url, restore_postgres_auth_backup


def main():
    parser = argparse.ArgumentParser(
        description="Restore Postgres auth users from a backup file."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the backup file created by backup_users_from_postgres.py",
    )
    args = parser.parse_args()

    database_url = normalize_database_url(os.environ.get("DATABASE_URL"))
    if not database_url:
        print("DATABASE_URL is not set. Export your Postgres connection string first.", file=sys.stderr)
        return 1

    counts = restore_postgres_auth_backup(database_url=database_url, backup_path=args.input)
    print("Postgres auth restore complete.")
    print(f"Backup file: {counts['backup_path']}")
    print(f"Users inserted: {counts['users']}")
    print(f"Licenses inserted: {counts['licenses']}")
    print(f"Password resets inserted: {counts['password_resets']}")
    print("Safe to re-run: duplicates are ignored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
