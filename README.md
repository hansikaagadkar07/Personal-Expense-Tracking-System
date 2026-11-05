# Pennywise – Personal Expense Tracking and Analysis System

## About

Pennywise is a web-based application that helps users record, manage, track, and analyze their personal expenses through a simple and user-friendly interface.

## Features

- User registration and login
- Secure password hashing
- Add, edit, delete, and view expenses
- Track income and monthly budgets
- View expense reports and charts
- Analyze monthly and category-wise spending
- Export expense data as CSV
- Separate personal records for each user

## Technologies Used

- Python
- Flask
- MySQL
- HTML, CSS, JavaScript
- Pandas, NumPy, Matplotlib
- PyMySQL

## Project Structure

- `app.py` – Main Flask application
- `config.py` – Database configuration
- `income.py` – Income management
- `export.py` – CSV export
- `setup_db.py` – Database setup
- `requirements.txt` – Required Python packages
- `templates/` – HTML templates
- `static/` – CSS, charts, and other static files

## How to Run

1. Clone the repository.
2. Install the required packages:

   `pip install -r requirements.txt`

3. Create a local `.env` file with your database configuration:

   - `DB_HOST`
   - `DB_USER`
   - `DB_PASSWORD`
   - `DB_NAME`
   - `SECRET_KEY`

4. Start the application:

   `python app.py`

5. Open http://127.0.0.1:5000 in your browser.

**Note:** Keep your `.env` file private. Do not upload passwords or secret keys to GitHub.
