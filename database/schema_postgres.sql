-- StaffScore database schema (PostgreSQL)
-- Create the "staffscore" database first (PostgreSQL cannot CREATE DATABASE
-- from inside a transaction / the same script that uses it), e.g.:
--     createdb staffscore
-- then run this file against that database:
--     psql -d staffscore -f schema_postgres.sql
--
-- v2: adds full salary + bonus system on top of the original
-- performance-tracking tables (salary_structure, spot_bonus, teams,
-- team_bonus, profit_sharing, referral_bonus, company_settings).

-- ============================================================
-- Core tables (unchanged from v1)
-- ============================================================

-- Basic employee details
CREATE TABLE IF NOT EXISTS employees (
    employee_id      SERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    department       VARCHAR(50)  NOT NULL,
    email            VARCHAR(120),
    phone            VARCHAR(20),
    base_salary      DECIMAL(10,2) NOT NULL DEFAULT 0, -- Deprecated: canonical salary is stored in salary_structure.monthly_base_salary
    experience_years INT NOT NULL DEFAULT 0,
    joining_year     INT
);

-- Login accounts. One row per person who can sign in; employees are linked
-- back to their employees row via employee_id (NULL for admin accounts).
 CREATE TABLE IF NOT EXISTS users ( 
    username VARCHAR(120) PRIMARY KEY, 
    password_hash VARCHAR(255) NOT NULL, 
    role VARCHAR(20) NOT NULL DEFAULT 'employee', 
    employee_id INT REFERENCES employees(employee_id) ON DELETE CASCADE, 
    failed_login_attempts INT NOT NULL DEFAULT 0, 
    locked_until TIMESTAMP NULL, 
    CHECK (role IN ('admin', 'employee')) 
    );

-- Month-wise raw performance numbers (used to calculate KPIs)
CREATE TABLE IF NOT EXISTS performance (
    performance_id             SERIAL PRIMARY KEY,
    employee_id                INT NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    month                      VARCHAR(7) NOT NULL,   -- format: YYYY-MM
    assigned_tasks             INT NOT NULL,
    completed_tasks            INT NOT NULL,
    completed_before_deadline  INT NOT NULL,
    working_days               INT NOT NULL,
    present_days                INT NOT NULL,
    customer_rating             DECIMAL(3,2) NOT NULL
);

-- Weights used in the Overall Score formula (single row, editable from Settings page)
CREATE TABLE IF NOT EXISTS score_weights (
    id                  INT PRIMARY KEY,
    task_weight         DECIMAL(4,3) NOT NULL,
    ontime_weight       DECIMAL(4,3) NOT NULL,
    satisfaction_weight DECIMAL(4,3) NOT NULL,
    attendance_weight   DECIMAL(4,3) NOT NULL
);

-- Performance-bonus slabs: % of BASIC (monthly base) salary awarded per
-- Overall Score range. Editable from Settings page.
CREATE TABLE IF NOT EXISTS bonus_policy (
    policy_id      SERIAL PRIMARY KEY,
    min_score      DECIMAL(5,2) NOT NULL,
    max_score      DECIMAL(5,2) NOT NULL,
    bonus_percent  DECIMAL(5,2) NOT NULL
);

-- ============================================================
-- NEW: Salary structure
-- ============================================================

-- Fixed monthly salary components per employee. One row per employee.
-- In Hand Salary = monthly_base_salary + hra + allowance + total_bonus
CREATE TABLE IF NOT EXISTS salary_structure (
    employee_id          INT PRIMARY KEY REFERENCES employees(employee_id) ON DELETE CASCADE,
    monthly_base_salary  DECIMAL(10,2) NOT NULL,   -- "basic salary" -- bonus % is applied to this
    hra                  DECIMAL(10,2) NOT NULL DEFAULT 0,
    allowance             DECIMAL(10,2) NOT NULL DEFAULT 0
);

-- ============================================================
-- NEW: Teams (for Team Bonus)
-- ============================================================

-- A team has exactly one manager (an employee). IT projects are usually
-- collaborative, so team bonuses reward the group rather than individuals.
CREATE TABLE IF NOT EXISTS teams (
    team_id     SERIAL PRIMARY KEY,
    team_name   VARCHAR(100) NOT NULL,
    manager_id  INT NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE
);

-- Which employees belong to which team (an employee can be on one or more teams)
CREATE TABLE IF NOT EXISTS team_members (
    team_id     INT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    employee_id INT NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, employee_id)
);

-- ============================================================
-- NEW: Bonus tables
-- ============================================================

-- Spot Bonus: one-time reward for an individual's exceptional contribution
-- (critical bug fix, emergency release, automation, client appreciation, etc.)
CREATE TABLE IF NOT EXISTS spot_bonus (
    spot_bonus_id   SERIAL PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    month           VARCHAR(7) NOT NULL,           -- format: YYYY-MM
    amount          DECIMAL(10,2) NOT NULL,
    reason_category VARCHAR(50) NOT NULL DEFAULT 'Other',
    notes           VARCHAR(255),
    CHECK (reason_category IN (
        'Critical Bug Fix', 'Emergency Release', 'Automation / Process Improvement',
        'Difficult Technical Problem', 'Exceptional Client Appreciation', 'Other'
    ))
);

-- Team Bonus: a bonus pool awarded to a whole team for team-level performance,
-- split evenly across that team's members when calculating each person's pay.
-- member_count_snapshot and member_ids_snapshot are frozen at award time so
-- future roster changes do not alter historical per-member shares or recipients
-- (Rank 5 payroll immutability).
CREATE TABLE IF NOT EXISTS team_bonus (
    team_bonus_id         SERIAL PRIMARY KEY,
    team_id               INT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    month                 VARCHAR(7) NOT NULL,
    total_amount          DECIMAL(10,2) NOT NULL,
    reason                VARCHAR(255),
    member_count_snapshot INT NOT NULL DEFAULT 0,  -- headcount at time of award
    member_ids_snapshot   TEXT                     -- JSON list of recipient employee_ids at award time
);

-- Profit-Sharing Bonus: company-wide profit pool for a period, split evenly
-- across every employee when calculating each person's pay.
-- e.g. company_profit = 10,00,00,000 and pool_percent = 5 -> pool_amount = 50,00,000
-- headcount is snapshotted at award time so future hires/exits do not alter
-- historical per-employee shares (Rank 5 payroll immutability).
CREATE TABLE IF NOT EXISTS profit_sharing (
    profit_sharing_id SERIAL PRIMARY KEY,
    period            VARCHAR(7) NOT NULL,        -- format: YYYY-MM (payout month)
    company_profit    DECIMAL(14,2) NOT NULL,
    pool_percent      DECIMAL(5,2) NOT NULL,
    pool_amount       DECIMAL(14,2) NOT NULL,     -- = company_profit * pool_percent / 100
    headcount         INT NOT NULL DEFAULT 0      -- employee count at time of award
);

-- Referral Bonus: paid to the referring employee once their referred
-- candidate is hired AND completes the required eligibility period.
CREATE TABLE IF NOT EXISTS referral_bonus (
    referral_id           SERIAL PRIMARY KEY,
    referrer_employee_id  INT NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    candidate_name        VARCHAR(100) NOT NULL,
    referral_date         DATE NOT NULL,
    hire_date             DATE,
    eligibility_status    VARCHAR(20) NOT NULL DEFAULT 'Pending',
    bonus_amount          DECIMAL(10,2) NOT NULL DEFAULT 25000,
    payout_month          VARCHAR(7),             -- set once status = 'Paid'
    CHECK (eligibility_status IN ('Pending', 'Hired', 'Eligible', 'Paid', 'Rejected'))
);

-- Company-wide bonus defaults, editable from Settings (single row, id = 1)
CREATE TABLE IF NOT EXISTS company_settings (
    id                           INT PRIMARY KEY,
    default_referral_bonus      DECIMAL(10,2) NOT NULL,
    default_profit_pool_percent DECIMAL(5,2) NOT NULL
);

-- Application settings (e.g. payslip configuration JSON, system-wide toggles)
CREATE TABLE IF NOT EXISTS app_settings (
    config_key   VARCHAR(100) PRIMARY KEY,
    config_value TEXT NOT NULL,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Departmental bonus budget tracking
CREATE TABLE IF NOT EXISTS bonus_budgets (
    budget_id        SERIAL PRIMARY KEY,
    department       VARCHAR(50) NOT NULL,
    period_type      VARCHAR(20) NOT NULL DEFAULT 'custom',
    period_start     DATE NOT NULL,
    period_end       DATE NOT NULL,
    allocated_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    notes            VARCHAR(255),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (department, period_start, period_end)
);

-- Central audit log trail (PostgreSQL, replacing local SQLite)
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id    SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    username  VARCHAR(120) NOT NULL,
    action    VARCHAR(255) NOT NULL,
    old_value TEXT DEFAULT '—',
    new_value TEXT DEFAULT '—'
);

-- ============================================================
-- Seed defaults (safe to re-run)
-- ============================================================

INSERT INTO score_weights (id, task_weight, ontime_weight, satisfaction_weight, attendance_weight)
VALUES (1, 0.35, 0.25, 0.20, 0.20)
ON CONFLICT (id) DO NOTHING;

INSERT INTO bonus_policy (policy_id, min_score, max_score, bonus_percent) VALUES
    (1, 90, 100, 15),
    (2, 60, 89.99, 7),
    (3, 0, 59.99, 0)
ON CONFLICT (policy_id) DO NOTHING;

INSERT INTO company_settings (id, default_referral_bonus, default_profit_pool_percent)
VALUES (1, 25000, 5.00)
ON CONFLICT (id) DO NOTHING;
