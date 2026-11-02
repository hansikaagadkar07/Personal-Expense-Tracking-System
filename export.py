import csv
import io
from datetime import datetime
from functools import wraps
from flask import Blueprint, Response, request, session, redirect, url_for, flash
import pymysql
import config

export_bp = Blueprint("export", __name__)


def get_db():
    return pymysql.connect(host=config.DB_HOST, user=config.DB_USER,
                           password=config.DB_PASSWORD, database=config.DB_NAME)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def check_date(value):
    try: datetime.strptime(value, "%Y-%m-%d"); return True
    except ValueError: return False


def safe(value):
    text = "" if value is None else str(value)
    if text and text[0] in "=+-@": return "'" + text
    return text


@export_bp.route("/export/expenses.csv")
@login_required
def export_expenses():
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    category = request.args.get("category", "")
    if start and not check_date(start): return "Invalid start date.", 400
    if end and not check_date(end): return "Invalid end date.", 400
    if category and not category.isdigit(): return "Invalid category.", 400
    sql = ("SELECT e.expense_id,e.expense_date,c.category_name,e.amount,"
           "e.description,e.payment_method FROM expenses e "
           "JOIN categories c ON e.category_id=c.category_id WHERE e.user_id=%s")
    params = [session["user_id"]]
    if start: sql += " AND e.expense_date >= %s"; params.append(start)
    if end: sql += " AND e.expense_date <= %s"; params.append(end)
    if category: sql += " AND e.category_id = %s"; params.append(category)
    sql += " ORDER BY e.expense_date,e.expense_id"
    conn = get_db(); cur = conn.cursor(); cur.execute(sql, params)
    rows = cur.fetchall(); conn.close()
    buffer = io.StringIO(); writer = csv.writer(buffer)
    writer.writerow(["ID","Date","Category","Amount","Description","Payment"])
    for row in rows: writer.writerow([safe(cell) for cell in row])
    filename = "expenses_" + datetime.now().strftime("%Y%m%d") + ".csv"
    return Response("\\ufeff" + buffer.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename="+filename})
