import os
import re
import time
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, flash, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import pandas as pd
import numpy as np
from matplotlib.figure import Figure

import config
from income import income_bp
from export import export_bp

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.register_blueprint(income_bp)
app.register_blueprint(export_bp)

PAYMENTS = ["Cash", "Card", "UPI"]
CHART_DIR = os.path.join(app.static_folder, "charts")
os.makedirs(CHART_DIR, exist_ok=True)


def get_db():
    return pymysql.connect(
        host=config.DB_HOST, user=config.DB_USER,
        password=config.DB_PASSWORD, database=config.DB_NAME
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def ensure_user_tables():
    """Safe additive migration. Existing expense/income rows are left untouched."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(150) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for table, column in [("expenses", "expense_id"), ("income", "income_id"),
                          ("budgets", "budget_id")]:
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME='user_id'
        """, (config.DB_NAME, table))
        if cur.fetchone()[0] == 0:
            cur.execute(f"ALTER TABLE `{table}` ADD COLUMN user_id INT NULL")
        index_name = f"idx_{table}_user_id"
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s
        """, (config.DB_NAME, table, index_name))
        if cur.fetchone()[0] == 0:
            cur.execute(f"CREATE INDEX `{index_name}` ON `{table}` (user_id)")
    # Replace the old single-user budget uniqueness rule with a per-user rule.
    # First create a separate category_id index so MySQL's foreign key does not
    # depend on the old UNIQUE(category_id, budget_month) index being removed.
    cur.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='budgets'
          AND INDEX_NAME='idx_budgets_category_id'
    """, (config.DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE INDEX idx_budgets_category_id ON budgets (category_id)")

    cur.execute("""
        SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS cols
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='budgets' AND NON_UNIQUE=0
          AND INDEX_NAME <> 'PRIMARY'
        GROUP BY INDEX_NAME
    """, (config.DB_NAME,))
    for index_name, cols in cur.fetchall():
        if cols == "category_id,budget_month":
            cur.execute(f"ALTER TABLE budgets DROP INDEX `{index_name}`")
    cur.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='budgets'
          AND INDEX_NAME='uq_budget_user_category_month'
    """, (config.DB_NAME,))
    if cur.fetchone()[0] == 0:
        cur.execute("""
            ALTER TABLE budgets ADD UNIQUE KEY uq_budget_user_category_month
            (user_id, category_id, budget_month)
        """)
    conn.commit()
    conn.close()


def ensure_budget_table():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            budget_id INT AUTO_INCREMENT PRIMARY KEY,
            category_id INT NOT NULL,
            budget_month CHAR(7) NOT NULL,
            budget_amount DECIMAL(10,2) NOT NULL CHECK (budget_amount > 0),
            UNIQUE (category_id, budget_month),
            FOREIGN KEY (category_id) REFERENCES categories(category_id)
        )
    """)
    conn.commit()
    conn.close()


ensure_budget_table()
ensure_user_tables()


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect("/")
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not name or len(name) > 100:
            flash("Enter a name (up to 100 characters).")
        elif not email or len(email) > 150 or "@" not in email:
            flash("Enter a valid email address.")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.")
        elif password != confirm:
            flash("Passwords do not match.")
        else:
            conn = get_db()
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO users (name,email,password) VALUES (%s,%s,%s)",
                    (name, email, generate_password_hash(password))
                )
                conn.commit()
                user_id = cur.lastrowid
                session.clear()
                session["user_id"] = user_id
                session["user_name"] = name
                session["user_email"] = email
                flash("Your account and profile have been created.")
                return redirect("/")
            except pymysql.err.IntegrityError:
                flash("An account with that email already exists. Please log in.")
            finally:
                conn.close()
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect("/")
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT user_id, name, email, password FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user[3], password):
            session.clear()
            session["user_id"] = user[0]
            session["user_name"] = user[1]
            session["user_email"] = user[2]
            flash("Welcome back.")
            return redirect("/")
        flash("Incorrect email or password.")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))


@app.route("/profile")
@login_required
def profile():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name,email,created_at FROM users WHERE user_id=%s", (session["user_id"],))
    user = cur.fetchone()
    conn.close()
    if not user:
        session.clear()
        return redirect(url_for("login"))
    return render_template("profile.html", user=user)


def read_amount():
    try:
        amount = float(request.form.get("amount", ""))
    except (ValueError, TypeError):
        return None
    return amount if amount > 0 else None


def valid_month(month):
    if not re.fullmatch(r"\d{4}-\d{2}", month or ""):
        return False
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        return False
    return True


def get_categories():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT category_id, category_name FROM categories ORDER BY category_name")
    rows = cur.fetchall()
    conn.close()
    return rows


def budget_rows(month):
    sql = """
        SELECT b.budget_id, c.category_name, b.budget_amount,
               COALESCE(SUM(e.amount), 0) AS spent
        FROM budgets b JOIN categories c ON b.category_id = c.category_id
        LEFT JOIN expenses e ON e.category_id = b.category_id
             AND DATE_FORMAT(e.expense_date, '%%Y-%%m') = b.budget_month
             AND e.user_id = b.user_id
        WHERE b.budget_month = %s AND b.user_id = %s
        GROUP BY b.budget_id, c.category_name, b.budget_amount
        ORDER BY c.category_name
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, (month, session["user_id"]))
    rows = cur.fetchall()
    conn.close()
    result = []
    for bid, name, budget, spent in rows:
        budget, spent = float(budget), float(spent)
        pct = spent / budget * 100
        status = "Over budget" if pct > 100 else "Near limit" if pct >= 80 else "OK"
        result.append({
            "id": bid, "name": name, "budget": f"{budget:.2f}",
            "spent": f"{spent:.2f}", "remaining": f"{budget-spent:.2f}",
            "pct": f"{pct:.0f}", "status": status
        })
    return result


def get_df(start, end, category):
    sql = ("SELECT e.expense_date, c.category_name, e.amount "
           "FROM expenses e JOIN categories c ON e.category_id=c.category_id "
           "WHERE e.user_id=%s")
    params = [session["user_id"]]
    if start:
        sql += " AND e.expense_date >= %s"; params.append(start)
    if end:
        sql += " AND e.expense_date <= %s"; params.append(end)
    if category:
        sql += " AND e.category_id = %s"; params.append(category)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    df = pd.DataFrame(rows, columns=["expense_date", "category_name", "amount"])
    if not df.empty:
        df["amount"] = df["amount"].astype(float)
        df["month"] = pd.to_datetime(df["expense_date"]).dt.strftime("%Y-%m")
    return df


def make_charts(cat, monthly):
    fig = Figure(figsize=(6, 5))
    ax = fig.subplots()
    ax.pie(cat.values, autopct="%1.1f%%")
    ax.legend(cat.index, title="Category", loc="center left", bbox_to_anchor=(1, 0.5))
    ax.set_title("Spending by Category (share of total)")
    fig.savefig(os.path.join(CHART_DIR, "pie.png"), bbox_inches="tight")
    fig = Figure(figsize=(6, 5))
    ax = fig.subplots()
    ax.bar(monthly.index, monthly.values, label="Total spent")
    ax.set_title("Monthly Spending")
    ax.set_xlabel("Month"); ax.set_ylabel("Amount (INR)")
    ax.tick_params(axis="x", rotation=45); ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(CHART_DIR, "bar.png"))


@app.route("/")
@login_required
def home():
    q = request.args.get("q", "").strip()
    sql = """
        SELECT e.expense_id, e.expense_date, c.category_name,
               e.amount, e.description, e.payment_method
        FROM expenses e JOIN categories c ON e.category_id=c.category_id
        WHERE e.user_id=%s
    """
    params = [session["user_id"]]
    if q:
        sql += " AND (e.description LIKE %s OR c.category_name LIKE %s)"
        like = f"%{q}%"; params.extend([like, like])
    sql += " ORDER BY e.expense_date DESC, e.expense_id DESC"
    conn = get_db(); cur = conn.cursor()
    cur.execute(sql, params); expenses = cur.fetchall(); conn.close()
    this_month = datetime.now().strftime("%Y-%m")
    warnings = [r for r in budget_rows(this_month) if r["status"] != "OK"]
    return render_template("index.html", categories=get_categories(), expenses=expenses,
                           payments=PAYMENTS, q=q, warnings=warnings, this_month=this_month)


@app.route("/add_category", methods=["POST"])
@login_required
def add_category():
    name = request.form.get("category_name", "").strip()
    if not name or len(name) > 50:
        flash("Category name must contain 1 to 50 characters."); return redirect("/")
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO categories (category_name) VALUES (%s)", (name,))
        conn.commit(); flash(f"Category '{name}' added.")
    except pymysql.err.IntegrityError:
        flash("That category already exists.")
    finally:
        conn.close()
    return redirect("/")


@app.route("/add", methods=["POST"])
@login_required
def add():
    amount = read_amount()
    if amount is None:
        flash("Amount must be a positive number."); return redirect("/")
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO expenses (user_id,expense_date,category_id,amount,description,payment_method) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (session["user_id"], request.form["expense_date"], request.form["category_id"],
         amount, request.form.get("description", ""), request.form.get("payment_method", "Cash"))
    )
    conn.commit(); conn.close(); flash("Expense added.")
    return redirect("/")


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
@login_required
def edit(expense_id):
    conn = get_db(); cur = conn.cursor()
    if request.method == "POST":
        amount = read_amount()
        if amount is None:
            conn.close(); flash("Amount must be a positive number."); return redirect(f"/edit/{expense_id}")
        cur.execute(
            "UPDATE expenses SET expense_date=%s,category_id=%s,amount=%s,description=%s,payment_method=%s "
            "WHERE expense_id=%s AND user_id=%s",
            (request.form["expense_date"], request.form["category_id"], amount,
             request.form.get("description", ""), request.form.get("payment_method", "Cash"),
             expense_id, session["user_id"])
        )
        conn.commit()
        changed = cur.rowcount
        conn.close()
        flash("Expense updated." if changed else "Expense not found.")
        return redirect("/")
    cur.execute(
        "SELECT expense_id,expense_date,category_id,amount,description,payment_method "
        "FROM expenses WHERE expense_id=%s AND user_id=%s", (expense_id, session["user_id"])
    )
    e = cur.fetchone(); conn.close()
    if e is None:
        flash("Expense not found."); return redirect("/")
    return render_template("edit.html", e=e, categories=get_categories(), payments=PAYMENTS)


@app.route("/delete/<int:expense_id>", methods=["POST"])
@login_required
def delete(expense_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE expense_id=%s AND user_id=%s",
                (expense_id, session["user_id"]))
    conn.commit(); deleted = cur.rowcount; conn.close()
    flash("Expense deleted." if deleted else "Expense not found.")
    return redirect("/")


@app.route("/budgets")
@login_required
def budgets():
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")
    if not valid_month(month):
        flash("Please choose a valid month."); return redirect("/budgets")
    return render_template("budgets.html", month=month, categories=get_categories(),
                           rows=budget_rows(month))


@app.route("/set_budget", methods=["POST"])
@login_required
def set_budget():
    month = request.form.get("budget_month", "")
    if not valid_month(month):
        flash("Please choose a valid month."); return redirect("/budgets")
    try: amount = float(request.form.get("amount", ""))
    except ValueError: amount = 0
    if amount <= 0:
        flash("Budget must be a positive number."); return redirect(f"/budgets?month={month}")
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO budgets (user_id,category_id,budget_month,budget_amount) VALUES (%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE budget_amount=VALUES(budget_amount)",
        (session["user_id"], request.form["category_id"], month, amount)
    )
    conn.commit(); conn.close(); flash("Budget saved.")
    return redirect(f"/budgets?month={month}")


@app.route("/delete_budget/<int:budget_id>", methods=["POST"])
@login_required
def delete_budget(budget_id):
    month = request.form.get("month", "")
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM budgets WHERE budget_id=%s AND user_id=%s",
                (budget_id, session["user_id"]))
    conn.commit(); conn.close(); flash("Budget removed.")
    return redirect(f"/budgets?month={month}" if valid_month(month) else "/budgets")


@app.route("/report")
@login_required
def report():
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    category = request.args.get("category", "")
    if start and end and start > end:
        flash("The 'From' date must be before the 'To' date."); return redirect("/report")
    ctx = dict(categories=get_categories(), start=start, end=end, category=category)
    df = get_df(start, end, category)
    if df.empty:
        return render_template("report.html", empty=True, **ctx)
    amounts = df["amount"].to_numpy()
    monthly = df.groupby("month")["amount"].sum()
    cat = df.groupby("category_name")["amount"].sum().sort_values(ascending=False)
    share = cat / cat.sum() * 100
    make_charts(cat, monthly)
    stats = dict(total=f"{np.sum(amounts):.2f}", count=len(amounts),
                 average=f"{np.mean(amounts):.2f}", median=f"{np.median(amounts):.2f}",
                 largest=f"{np.max(amounts):.2f}", top_category=cat.index[0],
                 top_month=monthly.idxmax())
    monthly_rows = [(m, f"{v:.2f}") for m, v in monthly.items()]
    cat_rows = [(n, f"{cat[n]:.2f}", f"{share[n]:.1f}") for n in cat.index]
    return render_template("report.html", empty=False, stats=stats,
                           stamp=int(time.time()), monthly=monthly_rows, cats=cat_rows, **ctx)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
