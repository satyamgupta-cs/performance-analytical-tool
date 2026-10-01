"""
Database connection + helper functions for StaffScore.

Supports BOTH MySQL and PostgreSQL. Which one is used is controlled by the
DB_TYPE environment variable (or the `database/db_config.json` file written
by the Settings page):

    DB_TYPE=mysql       -> uses mysql-connector-python
    DB_TYPE=postgres    -> uses psycopg2                (default)

This means you and a friend can each run the exact same codebase against
whichever database engine you already have installed, without touching any
code — just set DB_TYPE (and the matching DB_HOST/DB_USER/... variables) in
your own environment, or pick the engine from the Settings page.

Connections are made through SQLAlchemy (create_engine + raw_connection()),
which:
  - safely URL-encodes host/user/password (so special characters like
    @ # % in a Postgres/pgAdmin password don't break the connection string),
  - pools connections and verifies them before use (pool_pre_ping), so a
    connection that went stale doesn't surface as a confusing driver error,
  - still hands back a plain DBAPI connection object (.cursor(), .commit(),
    .close()), so the rest of this file — which uses plain `%s`-placeholder
    SQL that both mysql-connector-python and psycopg2 accept — is unchanged.
"""

import json
import os
import re
import secrets
import string
from decimal import Decimal
import sqlite3
from datetime import datetime
import bcrypt
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv()  # reads .env in the project root into os.environ, if present

# --------------------------------------------------------------------------
# Engine selection
# --------------------------------------------------------------------------

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "database", "db_config.json")

_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

DB_FILE = "app_database.db"

def _load_saved_config():
    """Load DB settings previously saved from the Settings page, if any."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_db_config(db_type, host, port, user, password, name):
    """Persist DB connection settings to database/db_config.json so the
    choice survives app restarts (used by the Settings page's DB switcher).
    Environment variables always take priority over this file."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(
            {
                "DB_TYPE": db_type,
                "DB_HOST": host,
                "DB_PORT": str(port),
                "DB_USER": user,
                "DB_PASSWORD": password,
                "DB_NAME": name,
            },
            f,
            indent=2,
        )


_saved = _load_saved_config()


def _setting(key, default):
    """Environment variable wins, then the saved config file, then default."""
    return os.environ.get(key, _saved.get(key, default))


# Postgres is the default now (StaffScore is most commonly run against a
# local pgAdmin/Postgres server); set DB_TYPE=mysql explicitly to use MySQL.
DB_TYPE = _setting("DB_TYPE", "postgres").strip().lower()  # "mysql" or "postgres"
DB_HOST = _setting("DB_HOST", "localhost")
DB_USER = _setting("DB_USER", "postgres" if DB_TYPE != "mysql" else "root")
# No hardcoded fallback password — leave it empty and require the user to
# set DB_PASSWORD (via .env or the Settings page) instead of shipping a
# real-looking default password in source control.
DB_PASSWORD = _setting("DB_PASSWORD", "")
DB_NAME = _setting("DB_NAME", "staffscore")
DB_PORT = _setting("DB_PORT", "3306" if DB_TYPE == "mysql" else "5432")

if DB_TYPE not in ("mysql", "postgres", "postgresql"):
    raise ValueError(
        f"Unsupported DB_TYPE '{DB_TYPE}'. Use 'mysql' or 'postgres'."
    )
if DB_TYPE == "postgresql":
    DB_TYPE = "postgres"

_DRIVERNAME = "mysql+mysqlconnector" if DB_TYPE == "mysql" else "postgresql+psycopg2"


def _make_engine(database):
    """Build a SQLAlchemy engine for the given database name (or None for a
    driver-level connection with no database selected, e.g. mysql before
    the target database exists). URL.create() takes care of escaping any
    special characters in the username/password."""
    url = URL.create(
        _DRIVERNAME,
        username=DB_USER or None,
        password=DB_PASSWORD or None,
        host=DB_HOST,
        port=int(DB_PORT),
        database=database,
    )
    return create_engine(url, pool_pre_ping=True)


# Main engine, pointed at DB_NAME — reused for every normal query.
_engine = _make_engine(DB_NAME)


def get_connection(with_database=True):
    """Return a DBAPI connection (via SQLAlchemy) to whichever engine
    DB_TYPE points at. with_database=False connects without selecting
    DB_NAME (used by init_schema, before the target database necessarily
    exists) — for Postgres that means connecting to its "postgres"
    maintenance database, which always exists."""
    if with_database:
        return _engine.raw_connection()
    if DB_TYPE == "mysql":
        return _make_engine(None).raw_connection()
    return _make_engine("postgres").raw_connection()


def hash_password(plain_password):
    """Hash a plaintext password for storage. Never store or compare
    passwords in plaintext."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _password_matches(plain_password, password_hash):
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Not a valid bcrypt hash (e.g. a leftover plaintext row) - never
        # treat it as a match.
        return False


def generate_temp_password(length=12):
    """Generate a random one-time password for a newly created account."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def current_db_info():
    """Small dict describing the active connection, shown in Settings."""
    return {"type": DB_TYPE, "host": DB_HOST, "port": DB_PORT, "name": DB_NAME, "user": DB_USER}



def run_query(query, params=None, fetch=False):
    """Run a single SQL query. If fetch=True, returns rows as a DataFrame."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params or ())
    result = None
    if fetch:
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        result = pd.DataFrame(rows, columns=columns)
        # DECIMAL/NUMERIC columns come back as Decimal objects (on both
        # drivers), which don't mix with plain floats in calculations.
        for col in result.columns:
            if result[col].apply(lambda x: isinstance(x, Decimal)).any():
                result[col] = result[col].astype(float)
    else:
        conn.commit()
    cursor.close()
    conn.close()
    return result


def _last_insert_id(cursor, returning_column):
    """Return the id of the row just inserted, on whichever engine is active.
    MySQL exposes it via cursor.lastrowid; Postgres needs a RETURNING clause
    added to the INSERT (the caller does this), and we just fetch it here."""
    if DB_TYPE == "mysql":
        return cursor.lastrowid
    return cursor.fetchone()[0]


# ==========================================================================
# Employees + performance
# ==========================================================================

def get_employees_df():
    return run_query("SELECT * FROM employees", fetch=True)


def get_performance_df():
    return run_query("SELECT * FROM performance", fetch=True)


def get_weights():
    df = run_query("SELECT * FROM score_weights WHERE id = 1", fetch=True)
    row = df.iloc[0]
    return {
        "task": float(row["task_weight"]),
        "ontime": float(row["ontime_weight"]),
        "satisfaction": float(row["satisfaction_weight"]),
        "attendance": float(row["attendance_weight"]),
    }


def update_weights(task, ontime, satisfaction, attendance):
    run_query(
        """UPDATE score_weights
           SET task_weight=%s, ontime_weight=%s, satisfaction_weight=%s, attendance_weight=%s
           WHERE id = 1""",
        (task, ontime, satisfaction, attendance),
    )


def get_bonus_policy():
    return run_query("SELECT * FROM bonus_policy ORDER BY min_score DESC", fetch=True)


def update_bonus_percent(policy_id, bonus_percent):
    run_query(
        "UPDATE bonus_policy SET bonus_percent=%s WHERE policy_id=%s",
        (bonus_percent, policy_id),
    )

def validate_employee_row(name, department, email, phone, month, assigned_tasks,
                           completed_tasks, completed_before_deadline, working_days,
                           present_days, customer_rating,
                           monthly_base_salary=0, hra=0, allowance=0):
    """Returns a list of human-readable problems with one employee record -
    an empty list means it's valid. Used by both the single add-employee
    form and bulk import, so neither path can insert data the other one
    would have rejected."""
    errors = []

    def _blank(value):
        return value is None or (isinstance(value, str) and not value.strip())

    if _blank(name):
        errors.append("Name is required.")
    if _blank(department):
        errors.append("Department is required.")

    for label, value in (
        ("Monthly base salary", monthly_base_salary),
        ("HRA", hra),
        ("Allowance", allowance),
    ):
        try:
            if float(value) < 0:
                errors.append(f"{label} cannot be negative (got {value}).")
        except (TypeError, ValueError):
            errors.append(f"{label} must be a number (got {value!r}).")

    try:
        rating = float(customer_rating)
        if not (0 <= rating <= 5):
            errors.append(f"Customer rating must be between 0 and 5 (got {rating}).")
    except (TypeError, ValueError):
        errors.append(f"Customer rating must be a number (got {customer_rating!r}).")

    for label, value in (
        ("Assigned tasks", assigned_tasks),
        ("Completed tasks", completed_tasks),
        ("Completed before deadline", completed_before_deadline),
        ("Working days", working_days),
        ("Present days", present_days),
    ):
        try:
            if float(value) < 0:
                errors.append(f"{label} cannot be negative (got {value}).")
        except (TypeError, ValueError):
            errors.append(f"{label} must be a number (got {value!r}).")

    try:
        if float(completed_tasks) > float(assigned_tasks):
            errors.append("Completed tasks cannot exceed assigned tasks.")
    except (TypeError, ValueError):
        pass  # already reported as non-numeric above

    try:
        if float(present_days) > float(working_days):
            errors.append("Present days cannot exceed working days.")
    except (TypeError, ValueError):
        pass

    return errors

def email_in_use(email):
    """True if an account with this email already exists as a login
    (users.username). Without this check, a second employee sharing an
    email would hit a raw UniqueViolation from Postgres/MySQL instead of
    a clear message."""
    email = str(email or "").strip()
    if not email:
        return False
    result = run_query("SELECT 1 FROM users WHERE username = %s", (email,), fetch=True)
    return not result.empty

def add_employee(name, department, email, phone, month, assigned_tasks,
                 completed_tasks, completed_before_deadline, working_days,
                 present_days, customer_rating,
                 monthly_base_salary=0, hra=0, allowance=0,
                 experience=0, joining_year=2026):
    """Create an employee record, salary structure, first performance entry,
    and (if an email is given) a login account with a random one-time
    password. Returns (employee_id, temp_password) - temp_password is None
    when no login account was created. The caller is responsible for
    showing the temp password to the admin exactly once; it is never
    stored in plaintext. Raises ValueError (with every problem found, not
    just the first) if the data doesn't pass validate_employee_row."""

    errors = validate_employee_row(
        name, department, email, phone, month, assigned_tasks,
        completed_tasks, completed_before_deadline, working_days,
        present_days, customer_rating, monthly_base_salary, hra, allowance,
    )
    if email_in_use(email):
        errors.append(f"Email '{email}' already has an account.")
    if errors:
        raise ValueError("; ".join(errors))

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT MAX(employee_id) FROM employees")
        max_id_result = cursor.fetchone()

        if max_id_result and max_id_result[0] is not None:
            new_id = int(max_id_result[0]) + 1
        else:
            new_id = 1001

        cursor.execute(
            """INSERT INTO employees
               (employee_id, name, department, email, phone, base_salary, experience_years, joining_year)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (new_id, name, department, email, phone, monthly_base_salary, experience, joining_year)
        )

        temp_password = None
        if email:
            temp_password = generate_temp_password()
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, employee_id) VALUES (%s, %s, 'employee', %s)",
                (email, hash_password(temp_password), new_id)
            )

        cursor.execute(
            """INSERT INTO performance
               (employee_id, month, assigned_tasks, completed_tasks, completed_before_deadline,
                working_days, present_days, customer_rating)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (new_id, month, assigned_tasks, completed_tasks, completed_before_deadline,
             working_days, present_days, customer_rating)
        )

        cursor.execute(
            """INSERT INTO salary_structure (employee_id, monthly_base_salary, hra, allowance)
               VALUES (%s,%s,%s,%s)""",
            (new_id, monthly_base_salary, hra, allowance)
        )

        conn.commit()
        return new_id, temp_password

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()

ALLOWED_COLUMN_TYPES = {"INT", "DECIMAL(5,2)", "VARCHAR(50)"}


def add_column_to_performance(column_name, column_type):
    """Add a new column to the performance table (basic ALTER TABLE).
    Quoting differs by engine (backticks for MySQL, double quotes for
    Postgres); the type keywords (INT/DECIMAL/VARCHAR) are the same on both.
    column_type is checked against a fixed whitelist rather than trusted
    as-is - it ends up concatenated into DDL, so accepting an arbitrary
    string here would let anyone who can reach this function run arbitrary
    SQL, regardless of what the calling UI offers as choices."""
    if not _IDENTIFIER_RE.match(column_name):
        raise ValueError("Column name must be letters, numbers, or underscores only.")
    if column_type not in ALLOWED_COLUMN_TYPES:
        raise ValueError(f"Column type must be one of: {', '.join(sorted(ALLOWED_COLUMN_TYPES))}.")
    quote = "`" if DB_TYPE == "mysql" else '"'
    query = f"ALTER TABLE performance ADD COLUMN {quote}{column_name}{quote} {column_type}"
    run_query(query)


REQUIRED_UPLOAD_COLUMNS = [
    "name", "department", "email", "phone", "month", "assigned_tasks",
    "completed_tasks", "completed_before_deadline", "working_days",
    "present_days", "customer_rating",
    "monthly_base_salary", "hra", "allowance",
]


def bulk_import_from_df(df):
    """Insert every row of an uploaded CSV/Excel file as a new employee +
    performance record + salary structure. Every row is validated before
    anything is inserted - if any row fails, nothing in the file is
    imported and the full list of problems is returned instead, so a bad
    row late in a large file can't leave the import half-done with no
    record of what happened. Checks both data validity (see
    validate_employee_row) and email collisions - against other rows in
    the same file, and against accounts that already exist.

    Returns (count, created_logins, errors):
      - validation failure: (0, [], ["Row 4 (Test User Four): ...", ...])
      - success: (row_count, [(name, email, temp_password), ...], [])
    """
    errors = []
    seen_emails = {}
    for i, row in df.iterrows():
        row_errors = validate_employee_row(*(row[col] for col in REQUIRED_UPLOAD_COLUMNS))

        email = str(row.get("email") or "").strip()
        if email:
            if email in seen_emails:
                row_errors.append(f"Duplicate email within this file (also used by row {seen_emails[email]}).")
            else:
                seen_emails[email] = i + 1
                if email_in_use(email):
                    row_errors.append(f"Email '{email}' already has an account.")

        if row_errors:
            label = row.get("name") or f"row {i + 1}"
            errors.extend(f"Row {i + 1} ({label}): {err}" for err in row_errors)

    if errors:
        return 0, [], errors

    created_logins = []
    for _, row in df.iterrows():
        _, temp_password = add_employee(*(row[col] for col in REQUIRED_UPLOAD_COLUMNS))
        if temp_password:
            created_logins.append((row["name"], row["email"], temp_password))
    return len(df), created_logins, []

def ensure_default_admin():
    """Create a default admin account if no admin exists yet. Returns the
    one-time plaintext password when a new account was created, or None if
    an admin already exists. Called from init_schema() so a fresh database
    always has a way to log in."""
    existing = run_query("SELECT username FROM users WHERE role = 'admin'", fetch=True)
    if existing is not None and not existing.empty:
        return None

    temp_password = generate_temp_password()
    run_query(
        "INSERT INTO users (username, password_hash, role, employee_id) VALUES (%s, %s, 'admin', NULL)",
        ("admin", hash_password(temp_password)),
    )
    return temp_password


# ==========================================================================
# Salary structure
# ==========================================================================
def get_salary_structure_df():
    return run_query("SELECT * FROM salary_structure", fetch=True)

def upsert_salary_structure(employee_id, monthly_base_salary, hra, allowance):
    """Insert the employee's salary structure if it doesn't exist yet,
    otherwise update it. Works the same way on both engines by checking
    first, rather than relying on an engine-specific "upsert" keyword."""
    existing = run_query(
        "SELECT employee_id FROM salary_structure WHERE employee_id=%s",
        (employee_id,), fetch=True,
    )
    if existing.empty:
        run_query(
            "INSERT INTO salary_structure (employee_id, monthly_base_salary, hra, allowance) "
            "VALUES (%s,%s,%s,%s)",
            (employee_id, monthly_base_salary, hra, allowance),
        )
    else:
        run_query(
            "UPDATE salary_structure SET monthly_base_salary=%s, hra=%s, allowance=%s "
            "WHERE employee_id=%s",
            (monthly_base_salary, hra, allowance, employee_id),
        )


# ==========================================================================
# Teams (for Team Bonus)
# ==========================================================================

def get_teams_df():
    """Teams joined with their manager's name, for display."""
    return run_query(
        """SELECT t.team_id, t.team_name, t.manager_id, e.name AS manager_name
           FROM teams t JOIN employees e ON e.employee_id = t.manager_id
           ORDER BY t.team_name""",
        fetch=True,
    )


def create_team(team_name, manager_id):
    conn = get_connection()
    cursor = conn.cursor()
    if DB_TYPE == "mysql":
        cursor.execute(
            "INSERT INTO teams (team_name, manager_id) VALUES (%s,%s)",
            (team_name, manager_id),
        )
        new_id = cursor.lastrowid
    else:
        cursor.execute(
            "INSERT INTO teams (team_name, manager_id) VALUES (%s,%s) RETURNING team_id",
            (team_name, manager_id),
        )
        new_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return new_id


def get_team_members_df():
    """Team membership joined with employee names, for display."""
    return run_query(
        """SELECT tm.team_id, t.team_name, tm.employee_id, e.name AS employee_name
           FROM team_members tm
           JOIN teams t ON t.team_id = tm.team_id
           JOIN employees e ON e.employee_id = tm.employee_id
           ORDER BY t.team_name, e.name""",
        fetch=True,
    )


def add_team_member(team_id, employee_id):
    """Add an employee to a team. Silently does nothing if already a member."""
    existing = run_query(
        "SELECT 1 FROM team_members WHERE team_id=%s AND employee_id=%s",
        (team_id, employee_id), fetch=True,
    )
    if existing.empty:
        run_query(
            "INSERT INTO team_members (team_id, employee_id) VALUES (%s,%s)",
            (team_id, employee_id),
        )


def remove_team_member(team_id, employee_id):
    run_query(
        "DELETE FROM team_members WHERE team_id=%s AND employee_id=%s",
        (team_id, employee_id),
    )


# ==========================================================================
# Spot Bonus (individual, one-time)
# ==========================================================================

SPOT_BONUS_REASONS = [
    "Critical Bug Fix", "Emergency Release", "Automation / Process Improvement",
    "Difficult Technical Problem", "Exceptional Client Appreciation", "Other",
]


def get_spot_bonus_df():
    return run_query(
        """SELECT sb.*, e.name AS employee_name
           FROM spot_bonus sb JOIN employees e ON e.employee_id = sb.employee_id
           ORDER BY sb.month DESC""",
        fetch=True,
    )


def add_spot_bonus(employee_id, month, amount, reason_category, notes=""):
    run_query(
        """INSERT INTO spot_bonus (employee_id, month, amount, reason_category, notes)
           VALUES (%s,%s,%s,%s,%s)""",
        (employee_id, month, amount, reason_category, notes),
    )


# ==========================================================================
# Team Bonus (team pool, split evenly among members)
# ==========================================================================

def get_team_bonus_df():
    return run_query(
        """SELECT tb.*, t.team_name
           FROM team_bonus tb JOIN teams t ON t.team_id = tb.team_id
           ORDER BY tb.month DESC""",
        fetch=True,
    )


def add_team_bonus(team_id, month, total_amount, reason=""):
    run_query(
        """INSERT INTO team_bonus (team_id, month, total_amount, reason)
           VALUES (%s,%s,%s,%s)""",
        (team_id, month, total_amount, reason),
    )


# ==========================================================================
# Profit-Sharing Bonus (company pool, split evenly among all employees)
# ==========================================================================

def get_profit_sharing_df():
    return run_query("SELECT * FROM profit_sharing ORDER BY period DESC", fetch=True)


def add_profit_sharing(period, company_profit, pool_percent):
    """Record a profit-sharing pool for a period. pool_amount is computed
    here (company_profit x pool_percent / 100) and stored alongside the
    inputs so historical records don't change if the % is edited later."""
    pool_amount = float(company_profit) * float(pool_percent) / 100
    run_query(
        """INSERT INTO profit_sharing (period, company_profit, pool_percent, pool_amount)
           VALUES (%s,%s,%s,%s)""",
        (period, company_profit, pool_percent, pool_amount),
    )
    return pool_amount


# ==========================================================================
# Referral Bonus
# ==========================================================================

REFERRAL_STATUSES = ["Pending", "Hired", "Eligible", "Paid", "Rejected"]


def get_referral_bonus_df():
    return run_query(
        """SELECT rb.*, e.name AS referrer_name
           FROM referral_bonus rb JOIN employees e ON e.employee_id = rb.referrer_employee_id
           ORDER BY rb.referral_date DESC""",
        fetch=True,
    )


def add_referral(referrer_employee_id, candidate_name, referral_date, bonus_amount):
    run_query(
        """INSERT INTO referral_bonus
           (referrer_employee_id, candidate_name, referral_date, bonus_amount, eligibility_status)
           VALUES (%s,%s,%s,%s,'Pending')""",
        (referrer_employee_id, candidate_name, referral_date, bonus_amount),
    )


def update_referral_status(referral_id, status, hire_date=None, payout_month=None):
    """Move a referral through Pending -> Hired -> Eligible -> Paid (or Rejected).
    hire_date is set once the candidate is hired; payout_month is set once
    the bonus is actually paid out."""
    run_query(
        """UPDATE referral_bonus
           SET eligibility_status=%s, hire_date=COALESCE(%s, hire_date),
               payout_month=COALESCE(%s, payout_month)
           WHERE referral_id=%s""",
        (status, hire_date, payout_month, referral_id),
    )

# ==========================================================================
# Bonus budgets (per-department and company-wide allocation vs. spend)
# ==========================================================================

def get_bonus_budgets_df():
    """All budget rows, most recently created first."""
    return run_query("SELECT * FROM bonus_budgets ORDER BY period_start DESC, department", fetch=True)


def bonus_budget_exists(department, period_start, period_end):
    """True if a budget already covers this exact department + date range -
    the table also enforces this with a UNIQUE constraint, but checking
    first lets the UI show a clear message instead of a raw DB error."""
    result = run_query(
        "SELECT 1 FROM bonus_budgets WHERE department=%s AND period_start=%s AND period_end=%s",
        (department, period_start, period_end), fetch=True,
    )
    return not result.empty


def add_bonus_budget(department, period_type, period_start, period_end, allocated_amount, notes=""):
    """Create one budget allocation - a specific department, or 'ALL' for
    the company-wide pool - covering one date range."""
    errors = []
    if not department or not str(department).strip():
        errors.append("Department is required (use 'ALL' for a company-wide pool).")
    try:
        if float(allocated_amount) < 0:
            errors.append(f"Allocated amount cannot be negative (got {allocated_amount}).")
    except (TypeError, ValueError):
        errors.append(f"Allocated amount must be a number (got {allocated_amount!r}).")
    if period_end < period_start:
        errors.append("Period end date cannot be before the start date.")
    if not errors and bonus_budget_exists(department, period_start, period_end):
        errors.append(f"A budget for '{department}' covering {period_start} to {period_end} already exists.")
    if errors:
        raise ValueError("; ".join(errors))

    run_query(
        """INSERT INTO bonus_budgets (department, period_type, period_start, period_end, allocated_amount, notes)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (department, period_type, period_start, period_end, allocated_amount, notes),
    )


def delete_bonus_budget(budget_id):
    run_query("DELETE FROM bonus_budgets WHERE budget_id = %s", (budget_id,))

# ==========================================================================
# Company-wide bonus defaults
# ==========================================================================

def get_company_settings():
    df = run_query("SELECT * FROM company_settings WHERE id = 1", fetch=True)
    row = df.iloc[0]
    return {
        "default_referral_bonus": float(row["default_referral_bonus"]),
        "default_profit_pool_percent": float(row["default_profit_pool_percent"]),
    }


def update_company_settings(default_referral_bonus, default_profit_pool_percent):
    run_query(
        """UPDATE company_settings
           SET default_referral_bonus=%s, default_profit_pool_percent=%s
           WHERE id = 1""",
        (default_referral_bonus, default_profit_pool_percent),
    )


# ==========================================================================
# Schema setup
# ==========================================================================

def init_schema():
    """Create the staffscore tables (and seed default weights/bonus policy/
    company settings) on whichever engine is currently configured, using the
    matching schema file. Safe to run more than once."""
    schema_file = "schema_mysql.sql" if DB_TYPE == "mysql" else "schema_postgres.sql"
    schema_path = os.path.join(os.path.dirname(__file__), "database", schema_file)
    with open(schema_path, "r") as f:
        sql_text = f.read()

    if DB_TYPE == "mysql":
        # mysql-connector-python can CREATE DATABASE and then USE it within
        # the same connection, so one connection (no database selected) is
        # enough for the whole script.
        conn = get_connection(with_database=False)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`")
        cursor.execute(f"USE `{DB_NAME}`")
        for statement in sql_text.split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)
        conn.commit()
    else:
        # Postgres can't CREATE DATABASE inside a script that also uses it,
        # so make sure the target database exists first (via the "postgres"
        # maintenance database), then run the rest against DB_NAME.
        admin_conn = get_connection(with_database=False)
        # admin_conn is a SQLAlchemy pool proxy; autocommit must be set on
        # the real underlying DBAPI connection (admin_conn.autocommit would
        # silently no-op on the proxy itself), since CREATE DATABASE can't
        # run inside a transaction block.
        admin_conn.dbapi_connection.autocommit = True
        admin_cursor = admin_conn.cursor()
        admin_cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not admin_cursor.fetchone():
            admin_cursor.execute(f'CREATE DATABASE "{DB_NAME}"')
        admin_cursor.close()
        admin_conn.close()

        conn = get_connection(with_database=True)
        cursor = conn.cursor()
        for statement in sql_text.split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)
        conn.commit()

    cursor.close()
    conn.close()
    return ensure_default_admin()


def verify_login(username, password):
    """Check credentials and return user details if valid. Passwords are
    never compared or stored in plaintext."""
    query = "SELECT username, role, employee_id, password_hash FROM users WHERE username=%s"
    user_df = run_query(query, (username,), fetch=True)
    if user_df.empty:
        return None
    user = user_df.iloc[0].to_dict()
    if not _password_matches(password, user["password_hash"]):
        return None
    user.pop("password_hash")
    return user

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def attempt_login(username, password):
    """Rate-limited login. Tracked server-side per username (not in
    Streamlit's session state, which is per-browser-session and trivially
    reset by opening a fresh session), so a scripted brute-force attempt
    gets locked out regardless of how many times it reconnects. Returns
    (user_or_None, error_message_or_None)."""
    account = run_query(
        "SELECT failed_login_attempts, locked_until FROM users WHERE username=%s",
        (username,), fetch=True,
    )

    if not account.empty:
        locked_until = account.iloc[0]["locked_until"]
        if locked_until is not None and pd.Timestamp(locked_until) > pd.Timestamp.now():
            minutes_left = max(1, int((pd.Timestamp(locked_until) - pd.Timestamp.now()).total_seconds() // 60) + 1)
            return None, f"Too many failed attempts. Try again in about {minutes_left} minute(s)."

    user = verify_login(username, password)

    if user:
        if not account.empty:
            run_query(
                "UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE username = %s",
                (username,),
            )
        return user, None

    if not account.empty:
        attempts = int(account.iloc[0]["failed_login_attempts"] or 0) + 1
        if attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            lock_until = (pd.Timestamp.now() + pd.Timedelta(minutes=LOCKOUT_MINUTES)).to_pydatetime()
            run_query(
                "UPDATE users SET failed_login_attempts = %s, locked_until = %s WHERE username = %s",
                (attempts, lock_until, username),
            )
        else:
            run_query(
                "UPDATE users SET failed_login_attempts = %s WHERE username = %s",
                (attempts, username),
            )

    return None, "Invalid credentials. Please try again."

def change_user_password(username, old_password, new_password):
    """Verifies the old password and updates it to the new one (for employees)."""
    user = verify_login(username, old_password)
    if user:
        run_query(
            "UPDATE users SET password_hash = %s WHERE username = %s",
            (hash_password(new_password), username),
        )
        log_audit_action(
            username=username,
            action="Password changed (self-service, own account)",
        )
        return True
    return False

def admin_reset_password(email, new_password):
    """Resets a user's password without knowing the old one - used by the
    self-service 'forgot password' recovery-code flow, and could also be
    called from an admin-facing reset in future."""
    try:
        run_query(
            "UPDATE users SET password_hash = %s WHERE username = %s",
            (hash_password(new_password), email),
        )
        log_audit_action(
            username=email,
            action="Password reset via recovery code",
        )
        return True
    except Exception as e:
        print(f"Error resetting password: {e}")
        return False
    
def get_all_performance_with_standing():
    """Calculates a composite total score dynamically and assigns department rankings."""
    query = """
    WITH CalculatedScores AS (
        SELECT 
            p.performance_id,
            e.employee_id,
            e.name AS "Employee Name",
            e.department AS "Department",
            p.month AS "Month",
            ROUND(
                (COALESCE(p.completed_tasks::numeric / NULLIF(p.assigned_tasks, 0), 0) * 50) +
                (COALESCE(p.present_days::numeric / NULLIF(p.working_days, 0), 0) * 30) +
                (COALESCE(p.customer_rating::numeric / 5.0, 0) * 20),
            1) AS total_score
        FROM employees e
        JOIN performance p ON e.employee_id = p.employee_id
    ),
    RankedData AS (
        SELECT 
            employee_id,
            "Employee Name",
            "Department",
            "Month",
            total_score AS "Total Score",
            PERCENT_RANK() OVER(
                PARTITION BY "Department" 
                ORDER BY total_score DESC
            ) as pct_rank
        FROM CalculatedScores
    )
    SELECT 
        employee_id,
        "Employee Name",
        "Department",
        "Month",
        "Total Score",
        CASE 
            WHEN pct_rank <= 0.10 THEN 'Top 10%%'
            WHEN pct_rank <= 0.25 THEN 'Top 25%%'
            ELSE 'Standard'
        END AS "Dept_Standing"
    FROM RankedData
    ORDER BY "Department", "Total Score" DESC;
    """
    return run_query(query, fetch=True)

def get_employee_raw_performance(user_identifier):
    """Fetches raw performance metrics by matching employee_id, email, or employee name."""
    query = """
    SELECT 
        p.assigned_tasks,
        p.completed_tasks,
        p.completed_before_deadline,
        p.working_days,
        p.present_days,
        p.customer_rating,
        e.employee_id,
        e.name AS "Employee Name"
    FROM performance p
    JOIN employees e ON p.employee_id = e.employee_id
    WHERE e.employee_id::text = %s 
       OR e.name = %s
    ORDER BY p.performance_id DESC
    LIMIT 1;
    """
    df = run_query(query, (str(user_identifier), str(user_identifier)), fetch=True)
    if df is not None and not df.empty:
        return df.iloc[0].to_dict()
    return None

def init_audit_log_table():
    """Creates the audit_logs table if it does not exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            old_value TEXT DEFAULT '—',
            new_value TEXT DEFAULT '—'
        )
    """
    )
    conn.commit()
    conn.close()


def log_audit_action(username: str, action: str, old_val: str = "—", new_val: str = "—"):
    """Inserts an entry into the audit_logs table."""
    init_audit_log_table()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        """
        INSERT INTO audit_logs (timestamp, username, action, old_value, new_value)
        VALUES (?, ?, ?, ?, ?)
    """,
        (timestamp_str, username, action, str(old_val), str(new_val)),
    )

    conn.commit()
    conn.close()


def get_audit_logs_df() -> pd.DataFrame:
    """Retrieves all audit logs ordered by timestamp descending."""
    init_audit_log_table()
    conn = sqlite3.connect(DB_FILE)
    query = """
        SELECT 
            timestamp AS "Date & Time",
            username AS "User",
            action AS "Action",
            old_value AS "Old Value",
            new_value AS "New Value"
        FROM audit_logs
        ORDER BY log_id DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df