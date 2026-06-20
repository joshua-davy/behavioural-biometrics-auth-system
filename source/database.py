import os
import sqlite3

# sets path to where app.py ran from
DB_PATH = os.path.join(os.path.dirname(__file__), "keystrokes.db")

def get_db():
    # create db connection
    # default returns tuple so allows column name access
    connect = sqlite3.connect(DB_PATH)
    connect.row_factory = sqlite3.Row
    return connect

def init_db():
    db = get_db()

# create both tables, run if new db
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            coverage_phrase TEXT,
            avg_dwell_ms FLOAT,
            std_dwell_ms FLOAT,
            avg_flight_ms FLOAT,
            std_flight_ms FLOAT,
            avg_latency_ms FLOAT,
            std_latency_ms FLOAT,
            avg_interval_ms FLOAT,
            std_interval_ms FLOAT,
            graphical_password_hash TEXT,
            mouse_avg_profile TEXT,
            mouse_std_profile TEXT,
            backup_code TEXT,
            backup_code_used INTEGER DEFAULT 0,
            registration_code_hash TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS combined_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            is_impostor INTEGER,
            keystroke_result TEXT,
            graphical_result TEXT,
            mouse_result TEXT,
            final_result TEXT,
            login_time_seconds FLOAT,
            keystroke_time FLOAT,
            graphical_time FLOAT,
            mouse_time FLOAT,
            login_attempt_number INTEGER,
            backup_used INTEGER DEFAULT 0,
            prompt_match INTEGER,
            graphical_selected_animal TEXT,
            graphical_selected_colour TEXT,
            keystroke_avg_z FLOAT,
            keystroke_max_z FLOAT,
            keystroke_similarity FLOAT,
            mouse_avg_z FLOAT,
            mouse_max_z FLOAT,
            mouse_similarity FLOAT,
            FAR FLOAT,
            FRR FLOAT,
            TAR FLOAT,
            TRR FLOAT
        )
    """)
    # add reg code, if db schema old format
    try:
        db.execute("ALTER TABLE users ADD COLUMN registration_code_hash TEXT")
    except sqlite3.OperationalError:
        pass

    db.commit()
    db.close()