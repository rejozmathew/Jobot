import sqlite3
import os

db_path = os.getenv("JOB_APPLIER_DB_PATH", "job_applier.db")
print(f"Migrating database at: {db_path}")
conn = sqlite3.connect(db_path)
c = conn.cursor()

columns = ["step_memory", "next_goal", "evaluation"]

for col in columns:
    try:
        c.execute(f"ALTER TABLE application_steps ADD COLUMN {col} TEXT")
        print(f"Added column {col}")
    except sqlite3.OperationalError as e:
        print(f"Column {col} likely exists: {e}")

conn.commit()
conn.close()
