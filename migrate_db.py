"""
One-time migration for an EXISTING StaffScore database (as opposed to
setup_db.py, which is for a brand new one).

This script only adds things that are missing - it never drops a table,
drops a column, or deletes a row. It is safe to run more than once.

What it checks:

  1. employees: adds base_salary, experience_years, joining_year if any
     are missing (existing rows get 0 / NULL, matching what the app
     already assumed).
  2. users: if the table doesn't exist yet, creates it. If it exists with
     the old plaintext `password` column, adds a `password_hash` column
     and hashes every existing plaintext password into it - the old
     `password` column is left in place (not dropped) so you can confirm
     logins still work before removing it yourself.
  3. Makes sure at least one admin account exists.

BACK UP YOUR DATABASE before running this, as with any schema change.

Run:
    python migrate_db.py
"""

from sqlalchemy import inspect, text

from db_utils import (
    _engine, DB_TYPE, DB_NAME, hash_password, ensure_default_admin,
)


def _existing_columns(table_name):
    inspector = inspect(_engine)
    if table_name not in inspector.get_table_names():
        return None
    return {col["name"] for col in inspector.get_columns(table_name)}


def migrate_employees():
    columns = _existing_columns("employees")
    if columns is None:
        print("No 'employees' table found - nothing to migrate here. "
              "Run setup_db.py instead if this is a brand new database.")
        return

    additions = {
        "base_salary": "DECIMAL(10,2) NOT NULL DEFAULT 0",
        "experience_years": "INT NOT NULL DEFAULT 0",
        "joining_year": "INT",
    }
    missing = [col for col in additions if col not in columns]
    if not missing:
        print("employees: all columns already present.")
        return

    with _engine.begin() as conn:
        for col in missing:
            conn.execute(text(f"ALTER TABLE employees ADD COLUMN {col} {additions[col]}"))
    print(f"employees: added missing column(s): {', '.join(missing)}")


def migrate_users():
    columns = _existing_columns("users")

    if columns is None:
        create_sql = (
            "CREATE TABLE users ("
            "username VARCHAR(120) PRIMARY KEY, "
            "password_hash VARCHAR(255) NOT NULL, "
            "role VARCHAR(20) NOT NULL DEFAULT 'employee', "
            "employee_id INT, "
            "FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE)"
        )
        with _engine.begin() as conn:
            conn.execute(text(create_sql))
        print("users: table did not exist, created it.")
        return

    if "password_hash" in columns:
        print("users: password_hash column already present - nothing to migrate.")
        return

    if "password" not in columns:
        raise RuntimeError(
            "users table exists but has neither 'password' nor 'password_hash'. "
            "Inspect the table manually before proceeding."
        )

    with _engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        rows = conn.execute(text("SELECT username, password FROM users")).fetchall()
        for username, plain_password in rows:
            conn.execute(
                text("UPDATE users SET password_hash = :hashed WHERE username = :username"),
                {"hashed": hash_password(plain_password or ""), "username": username},
            )
    print(f"users: hashed {len(rows)} existing plaintext password(s) into password_hash.")
    print("The old 'password' column was left in place. Once you've confirmed logins "
          "work, drop it yourself, e.g.:")
    print("  ALTER TABLE users DROP COLUMN password;")



def migrate_bonus_budgets_table():
    """Creates the bonus_budgets table if it doesn't exist yet."""
    if _existing_columns("bonus_budgets") is not None:
        print("bonus_budgets: table already present.")
        return

    if DB_TYPE == "mysql":
        create_sql = (
            "CREATE TABLE bonus_budgets ("
            "budget_id INT PRIMARY KEY AUTO_INCREMENT, "
            "department VARCHAR(50) NOT NULL, "
            "period_type VARCHAR(20) NOT NULL DEFAULT 'custom', "
            "period_start DATE NOT NULL, "
            "period_end DATE NOT NULL, "
            "allocated_amount DECIMAL(12,2) NOT NULL DEFAULT 0, "
            "notes VARCHAR(255), "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "UNIQUE KEY uniq_budget (department, period_start, period_end))"
        )
    else:
        create_sql = (
            "CREATE TABLE bonus_budgets ("
            "budget_id SERIAL PRIMARY KEY, "
            "department VARCHAR(50) NOT NULL, "
            "period_type VARCHAR(20) NOT NULL DEFAULT 'custom', "
            "period_start DATE NOT NULL, "
            "period_end DATE NOT NULL, "
            "allocated_amount DECIMAL(12,2) NOT NULL DEFAULT 0, "
            "notes VARCHAR(255), "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "UNIQUE (department, period_start, period_end))"
        )
    with _engine.begin() as conn:
        conn.execute(text(create_sql))
    print("bonus_budgets: table created.")

if __name__ == "__main__":
    print(f"Connected to {DB_TYPE} database '{DB_NAME}'. Back up before continuing.")
    migrate_employees()
    migrate_users()
    migrate_bonus_budgets_table()
    admin_password = ensure_default_admin()
    if admin_password:
        print()
        print("No admin account existed, so one was created:")
        print("  username: admin")
        print(f"  password: {admin_password}")
        print("Save this now - it will not be shown again.")
    else:
        print("An admin account already exists.")