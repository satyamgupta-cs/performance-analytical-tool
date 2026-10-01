-- StaffScore database schema (MySQL)
-- Run this once to create the database + tables, or let the app's
-- setup helper do it for you (Settings -> "Create / verify tables").
-- NOTE: the app's init_schema() helper already runs its own
-- `CREATE DATABASE IF NOT EXISTS <your DB_NAME>` + `USE <your DB_NAME>`
-- before executing this file, so this file intentionally does NOT
-- hardcode a database name — running the two statements below by hand
-- would silently create everything in a database literally named
-- "staffscore" regardless of what DB_NAME you've configured.
--
-- To run this file by hand instead, create/select your database first, e.g.:
--     mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS your_db_name"
--     mysql -u root -p your_db_name < schema_mysql.sql
--
-- v2: adds full salary + bonus system on top of the original
-- performance-tracking tables (salary_structure, spot_bonus, teams,
-- team_bonus, profit_sharing, referral_bonus, company_settings).

-- ============================================================
-- Core tables (unchanged from v1)
-- ============================================================

-- Basic employee details
CREATE TABLE IF NOT EXISTS employees (
    employee_id      INT PRIMARY KEY AUTO_INCREMENT,
    name             VARCHAR(100) NOT NULL,
    department       VARCHAR(50)  NOT NULL,
    email            VARCHAR(120),
    phone            VARCHAR(20),
    base_salary      DECIMAL(10,2) NOT NULL DEFAULT 0,
    experience_years INT NOT NULL DEFAULT 0,
    joining_year     INT
);

-- Login accounts. One row per person who can sign in; employees are linked
-- back to their employees row via employee_id (NULL for admin accounts).
CREATE TABLE IF NOT EXISTS users (
    username      VARCHAR(120) PRIMARY KEY,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20) NOT NULL DEFAULT 'employee',
    employee_id   INT,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

-- Month-wise raw performance numbers (used to calculate KPIs)
CREATE TABLE IF NOT EXISTS performance (
    performance_id             INT PRIMARY KEY AUTO_INCREMENT,
    employee_id                INT NOT NULL,
    month                      VARCHAR(7) NOT NULL,   -- format: YYYY-MM
    assigned_tasks             INT NOT NULL,
    completed_tasks            INT NOT NULL,
    completed_before_deadline  INT NOT NULL,
    working_days               INT NOT NULL,
    present_days                INT NOT NULL,
    customer_rating             DECIMAL(3,2) NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

-- Weights used in the Overall Score formula (single row, editable from Settings page)
CREATE TABLE IF NOT EXISTS score_weights (
    id                 INT PRIMARY KEY,
    task_weight        DECIMAL(4,3) NOT NULL,
    ontime_weight      DECIMAL(4,3) NOT NULL,
    satisfaction_weight DECIMAL(4,3) NOT NULL,
    attendance_weight  DECIMAL(4,3) NOT NULL
);

-- Performance-bonus slabs: % of BASIC (monthly base) salary awarded per
-- Overall Score range. Editable from Settings page.
CREATE TABLE IF NOT EXISTS bonus_policy (
    policy_id      INT PRIMARY KEY AUTO_INCREMENT,
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
    employee_id          INT PRIMARY KEY,
    monthly_base_salary  DECIMAL(10,2) NOT NULL,   -- "basic salary" -- bonus % is applied to this
    hra                  DECIMAL(10,2) NOT NULL DEFAULT 0,
    allowance             DECIMAL(10,2) NOT NULL DEFAULT 0,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

-- ============================================================
-- NEW: Teams (for Team Bonus)
-- ============================================================

-- A team has exactly one manager (an employee). IT projects are usually
-- collaborative, so team bonuses reward the group rather than individuals.
CREATE TABLE IF NOT EXISTS teams (
    team_id     INT PRIMARY KEY AUTO_INCREMENT,
    team_name   VARCHAR(100) NOT NULL,
    manager_id  INT NOT NULL,
    FOREIGN KEY (manager_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

-- Which employees belong to which team (an employee can be on one or more teams)
CREATE TABLE IF NOT EXISTS team_members (
    team_id     INT NOT NULL,
    employee_id INT NOT NULL,
    PRIMARY KEY (team_id, employee_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

-- ============================================================
-- NEW: Bonus tables
-- ============================================================

-- Spot Bonus: one-time reward for an individual's exceptional contribution
-- (critical bug fix, emergency release, automation, client appreciation, etc.)
CREATE TABLE IF NOT EXISTS spot_bonus (
    spot_bonus_id   INT PRIMARY KEY AUTO_INCREMENT,
    employee_id     INT NOT NULL,
    month           VARCHAR(7) NOT NULL,           -- format: YYYY-MM
    amount          DECIMAL(10,2) NOT NULL,
    reason_category VARCHAR(50) NOT NULL DEFAULT 'Other',
    notes           VARCHAR(255),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    CHECK (reason_category IN (
        'Critical Bug Fix', 'Emergency Release', 'Automation / Process Improvement',
        'Difficult Technical Problem', 'Exceptional Client Appreciation', 'Other'
    ))
);

-- Team Bonus: a bonus pool awarded to a whole team for team-level performance,
-- split evenly across that team's members when calculating each person's pay.
CREATE TABLE IF NOT EXISTS team_bonus (
    team_bonus_id INT PRIMARY KEY AUTO_INCREMENT,
    team_id       INT NOT NULL,
    month         VARCHAR(7) NOT NULL,
    total_amount  DECIMAL(10,2) NOT NULL,
    reason        VARCHAR(255),
    FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE
);

-- Profit-Sharing Bonus: company-wide profit pool for a period, split evenly
-- across every employee when calculating each person's pay.
-- e.g. company_profit = 10,00,00,000 and pool_percent = 5 -> pool_amount = 50,00,000
CREATE TABLE IF NOT EXISTS profit_sharing (
    profit_sharing_id INT PRIMARY KEY AUTO_INCREMENT,
    period            VARCHAR(7) NOT NULL,        -- format: YYYY-MM (payout month)
    company_profit    DECIMAL(14,2) NOT NULL,
    pool_percent      DECIMAL(5,2) NOT NULL,
    pool_amount       DECIMAL(14,2) NOT NULL      -- = company_profit * pool_percent / 100
);

-- Referral Bonus: paid to the referring employee once their referred
-- candidate is hired AND completes the required eligibility period.
CREATE TABLE IF NOT EXISTS referral_bonus (
    referral_id           INT PRIMARY KEY AUTO_INCREMENT,
    referrer_employee_id  INT NOT NULL,
    candidate_name        VARCHAR(100) NOT NULL,
    referral_date         DATE NOT NULL,
    hire_date             DATE,
    eligibility_status    VARCHAR(20) NOT NULL DEFAULT 'Pending',
    bonus_amount          DECIMAL(10,2) NOT NULL DEFAULT 25000,
    payout_month          VARCHAR(7),             -- set once status = 'Paid'
    FOREIGN KEY (referrer_employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    CHECK (eligibility_status IN ('Pending', 'Hired', 'Eligible', 'Paid', 'Rejected'))
);

-- Company-wide bonus defaults, editable from Settings (single row, id = 1)
CREATE TABLE IF NOT EXISTS company_settings (
    id                           INT PRIMARY KEY,
    default_referral_bonus      DECIMAL(10,2) NOT NULL,
    default_profit_pool_percent DECIMAL(5,2) NOT NULL
);

-- ============================================================
-- Seed defaults (safe to re-run)
-- ============================================================

INSERT IGNORE INTO score_weights (id, task_weight, ontime_weight, satisfaction_weight, attendance_weight)
VALUES (1, 0.35, 0.25, 0.20, 0.20);

INSERT IGNORE INTO bonus_policy (policy_id, min_score, max_score, bonus_percent) VALUES
    (1, 90, 100, 15),
    (2, 60, 89.99, 7),
    (3, 0, 59.99, 0);

INSERT IGNORE INTO company_settings (id, default_referral_bonus, default_profit_pool_percent)
VALUES (1, 25000, 5.00);
