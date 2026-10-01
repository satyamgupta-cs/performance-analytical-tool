# StaffScore

Employee Performance Analytics & Salary/Bonus Recommendation System.
Built with Streamlit, pandas, and **either MySQL or PostgreSQL**.

## What's new in this version (v2)

- **Full Salary & Bonus system.** Every employee now has a salary structure
  (Monthly Base Salary + HRA + Allowance) and an **In Hand Salary** that adds
  up five kinds of bonus — see [Salary & Bonus model](#salary--bonus-model)
  below.
- **New "Bonuses & Teams" page** to record Spot Bonuses, Team Bonuses,
  Profit-Sharing pools and Referral Bonuses, and to set up teams + managers.
- **Works with MySQL or PostgreSQL.** Pick whichever database engine you (or a
  friend running their own copy of this app) already have installed — no code
  changes needed, just an environment variable or a setting on the Settings page.
- **Flagged Employees on the Dashboard.** A new section detects employees whose
  performance changed suddenly (a jump or a drop) using a one-way **ANOVA** test,
  and lets you drill into any flagged employee's trend right there, or jump to
  their full profile on the Employee page.

## Project structure

```
StaffScore/
├── app.py                        # Home page
├── db_utils.py                    # MySQL + PostgreSQL connection and all database read/write functions
├── calculations.py                # KPI, Overall Score, and Salary/Bonus formulas
├── anomaly_detection.py           # ANOVA-based "sudden performance change" detection
├── database/
│   ├── schema_mysql.sql           # Table definitions for MySQL
│   ├── schema_postgres.sql        # Table definitions for PostgreSQL
│   └── db_config.json             # Written automatically by the Settings page (git-ignore this)
├── pages/
│   ├── 1_Dashboard.py             # KPIs, salary/bonus totals, charts, Flagged Employees section
│   ├── 2_Dataset.py               # Employee ranking + add/import employees (with salary)
│   ├── 3_Employee.py              # Full profile incl. Salary & Bonus breakdown, ANOVA flag
│   ├── 4_Settings.py              # DB engine, score weights, bonus policy, salary, company defaults
│   └── 5_Bonuses_and_Teams.py     # Teams, Spot/Team/Profit-Sharing/Referral bonus entry
├── .env.example
└── requirements.txt
```

## Setup

1. **Install and start a database** — either works:
   - MySQL (e.g. via XAMPP/WAMP or a local MySQL server), or
   - PostgreSQL (e.g. via a local install or `postgres.app`).

2. **Install Python dependencies:**
   ```
   pip install -r requirements.txt
   ```

3. **Tell the app which database to use.** Copy `.env.example` to `.env` (or just
   export the variables yourself) and set:
   ```
   DB_TYPE=mysql        # or: postgres
   DB_HOST=localhost
   DB_PORT=3306         # 5432 for postgres
   DB_USER=root
   DB_PASSWORD=your-password
   DB_NAME=staffscore
   ```
   This is the easiest way for you and a friend to each run the app against
   your own preferred engine without editing any code — you just set different
   environment variables. If you'd rather not use environment variables, run
   the app once and set these from the **Settings → Database Connection**
   panel instead; it's saved to `database/db_config.json` for next time.

4. **Create the tables and the first admin login.**
   - **Brand new database:** run
     ```
     python setup_db.py
     ```
     This creates the tables (safe to run more than once) and, the first
     time, creates an `admin` account with a random one-time password
     printed to the terminal — save it, it will not be shown again.
   - **Existing database from an earlier version of StaffScore:** run
     ```
     python migrate_db.py
     ```
     instead. It only adds what's missing (new `employees` columns, a
     `users` table if you don't have one, or a `password_hash` column with
     your existing plaintext passwords hashed into it if you do) — it never
     drops a table, column, or row. Back up your database first, as with
     any schema change.

   Either way, table creation from **Settings → Database Connection →
   "Create / verify tables on this database"** requires being logged in as
   an admin already, so the first run has to happen from the terminal.

5. **Run the app:**
   ```
   streamlit run app.py
   ```
   Log in with `admin` and the password from step 4, then change it from
   the employee "Change Password" flow or reset it for others from Settings.

6. Add employees (with their salary structure) either one at a time or in bulk
   from the **Dataset** page (CSV/Excel upload, or the "Add a new employee
   record" form). Each employee with an email gets a random one-time login
   password shown once when they're added — pass it to them securely and have
   them change it after signing in. Set up teams, and record Spot/Team/Profit-
   Sharing/Referral bonuses, from the **Bonuses & Teams** page.

## Formulas used

### Performance score

| Metric | Formula |
|---|---|
| Task Completion Rate | (Completed_Tasks / Assigned_Tasks) x 100 |
| On-Time Delivery Rate | (Completed_Before_Deadline / Completed_Tasks) x 100 |
| Customer Satisfaction | (Customer Rating / 5) x 100 |
| Attendance Rate | (Present_Days / Working_Days) x 100 |
| Overall Score | 0.35xTask + 0.25xOnTime + 0.20xSatisfaction + 0.20xAttendance |

| Performance Score | Performance Bonus (% of Monthly Base Salary) |
|---|---|
| 90 and above | 15% |
| 60-89.99 | 7% |
| Below 60 | No Bonus |

Weights and bonus percentages can be changed from the **Settings** page —
the change is saved to the database and reflected everywhere else immediately.

### Salary & Bonus model

```
In Hand Salary = Monthly Base Salary + HRA + Allowance + Total Bonus

Total Bonus = Performance Bonus + Spot Bonus + Team Bonus
            + Profit-Sharing Bonus + Referral Bonus
```

| Bonus type | What it rewards | How it's calculated |
|---|---|---|
| **Performance Bonus** | Individual Overall Score | `Monthly Base Salary x Bonus_Percent / 100`, using the slab from the score table above |
| **Spot Bonus** | A one-time exceptional contribution (critical bug fix, emergency release, a time-saving automation, a hard technical problem solved, exceptional client appreciation) | Entered directly as a one-time amount against an employee and month |
| **Team Bonus** | Collaborative, hard-to-separate team output | A total pool entered against a team + month, split evenly across that team's current members |
| **Profit-Sharing Bonus** | Overall company profitability | A pool = `Company Profit x Pool %` entered per period, split evenly across every employee (e.g. ₹10 crore profit x 5% pool = ₹50 lakh, divided company-wide) |
| **Referral Bonus** | A successful employee referral | A fixed amount (default ₹25,000, configurable) paid once the referral moves through Pending → Hired → Eligible → **Paid** |

All bonus components are recorded on the **Bonuses & Teams** page (teams are
set up there too) and totalled up automatically on the **Employee** page's
Salary & Bonus breakdown and the **Dashboard**'s salary KPIs, for whichever
date range is selected.

## Flagged Employees (ANOVA sudden-change detection)

On the **Dashboard**, below the charts, StaffScore looks at every employee's
monthly Overall Score history and:

1. Splits it chronologically into an earlier **baseline** period and a later
   **recent** period.
2. Runs a one-way ANOVA (`scipy.stats.f_oneway`) comparing the two periods.
3. Flags the employee when the difference is **both**:
   - statistically significant (ANOVA p-value below the chosen alpha, default `0.05`), and
   - practically meaningful (the score moved by at least the chosen minimum
     number of points, default `10`).

This avoids flagging employees whose score just wobbles a little from month
to month, while still catching genuine sudden jumps (recognise/reward) or
drops (step in early). Detection thresholds (alpha, minimum point swing,
minimum months of history required) can be tuned right on the Dashboard.

Each flagged employee gets an expandable card showing their trend chart and
the ANOVA stats, plus an **"Open full profile"** button that jumps straight
to the Employee page with that employee pre-searched. Employees need at
least 4 months of history (configurable) before they can be tested at all.
