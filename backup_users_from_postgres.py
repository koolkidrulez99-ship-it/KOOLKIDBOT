import argparse
import os
import sys

from auth_storage import export_postgres_auth_backup, normalize_database_url


def main():
    parser = argparse.ArgumentParser(
        description="Export Postgres auth users to a backup file."
    )
    parser.add_argument(
        "--output",
        default="auth_users_backup.json",
        help="Path to the backup file to write. Default: auth_users_backup.json",
    )
    args = parser.parse_args()

    database_url = normalize_database_url(os.environ.get("DATABASE_URL"))
    if not database_url:
        print("DATABASE_URL is not set. Export your Postgres connection string first.", file=sys.stderr)
        return 1

    payload = export_postgres_auth_backup(database_url=database_url, backup_path=args.output)
    print("Postgres auth backup complete.")
    print(f"Backup file: {args.output}")
    print(f"Users exported: {len(payload.get('users', []))}")
    print(f"Licenses exported: {len(payload.get('licenses', []))}")
    print(f"Password resets exported: {len(payload.get('password_resets', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
