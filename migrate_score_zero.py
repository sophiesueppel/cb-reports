"""
One-time migration: set score=0 for all speeches where relevant_to_mp=0
and score is not already 0. Saves original score in original_score column.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/speeches.db")

conn = sqlite3.connect(str(DB_PATH))

# Add original_score column if needed
cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
if "original_score" not in cols:
    conn.execute("ALTER TABLE speeches ADD COLUMN original_score INTEGER")
    conn.commit()
    print("Added original_score column")

# Count before
before = conn.execute(
    "SELECT COUNT(*) FROM speeches WHERE relevant_to_mp=0 AND score != 0 AND score IS NOT NULL"
).fetchone()[0]
print(f"Speeches to migrate (relevant_to_mp=0, score!=0): {before}")

# Show breakdown by bank
rows = conn.execute(
    "SELECT central_bank, COUNT(*) FROM speeches WHERE relevant_to_mp=0 AND score != 0 AND score IS NOT NULL GROUP BY central_bank"
).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

# Migrate: copy score -> original_score, set score=0
conn.execute("""
    UPDATE speeches
    SET original_score = score, score = 0
    WHERE relevant_to_mp = 0
      AND score != 0
      AND score IS NOT NULL
      AND original_score IS NULL
""")
conn.commit()

after = conn.execute(
    "SELECT COUNT(*) FROM speeches WHERE score = 0"
).fetchone()[0]
print(f"\nSpeeches now with score=0: {after}")

# Verify
check = conn.execute(
    "SELECT COUNT(*) FROM speeches WHERE relevant_to_mp=0 AND score != 0 AND score IS NOT NULL"
).fetchone()[0]
print(f"Remaining un-migrated (should be 0): {check}")

conn.close()
print("Done.")
