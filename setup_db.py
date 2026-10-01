"""
One-time setup: creates the StaffScore tables on the configured database
and prints the first admin login if one doesn't exist yet.

Run this once before starting the app for the first time:

    python setup_db.py

DB_TYPE / DB_HOST / DB_USER / etc. are read the same way the app reads
them (.env file, environment variables, or database/db_config.json).
"""

from db_utils import init_schema, current_db_info

if __name__ == "__main__":
    info = current_db_info()
    print(f"Connecting to {info['type']} at {info['host']}:{info['port']}, database '{info['name']}'...")

    admin_password = init_schema()
    print("Tables created (or already existed).")

    if admin_password:
        print()
        print("Admin account created:")
        print("  username: admin")
        print(f"  password: {admin_password}")
        print()
        print("Save this password now - it will not be shown again. "
              "Change it after your first login.")
    else:
        print("An admin account already exists; no new one was created.")
