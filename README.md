# Pennywise – Personal Expense Tracking and Analysis System

## Features
- Register, log in, log out, and view a profile
- Passwords are stored as secure password hashes (not plain text)
- Each account sees and manages only its own expenses, income, budgets, reports and CSV exports
- Add/edit/delete/search expenses and add shared category labels
- Monthly budgets, income/savings summaries, Pandas/NumPy analysis and Matplotlib charts

## Setup
1. Keep your existing MySQL database. **Do not run `setup_db.py`** on a database containing data: that script drops existing tables.
2. Create a `.env` file beside `app.py` and `config.py`, using `.env.example` as a template. Enter your own MySQL password locally; never upload `.env` or share its contents.
3. Activate your existing virtual environment and install packages:
   `python -m pip install -r requirements.txt`
4. Start the app from this folder:
   `python app.py`
5. Open `http://127.0.0.1:5000/register` and create an account. Registration automatically creates the user's profile and signs them in.
6. Later, use `/login` to sign in. Use the Profile link to view account details and Log out to end the session.

## Database migration and existing records
On startup the app creates the `users` table if needed and adds nullable `user_id` columns/indexes to expenses, income and budgets. It also changes the budget uniqueness rule so each account can have its own budget for the same category and month.

This is an additive migration: it does not delete existing expense, income or budget rows. Older records with `user_id = NULL` are intentionally not shown to newly registered accounts, because assigning old shared records to the first account could expose data. If you need old demo records, decide which account should own them and assign their IDs in MySQL only after checking with your team.

Categories remain a shared list of category names; financial records themselves are separated by account.

## Important
- Use fictional test data for demonstrations.
- Set a strong, private `SECRET_KEY` in `.env` before using the app beyond a local class demo.
- The Flask development server is for local learning/demo use, not public production hosting.
