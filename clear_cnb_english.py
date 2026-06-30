import sqlite3
conn = sqlite3.connect("data/speeches.db")
cur = conn.cursor()
cur.execute("DELETE FROM speeches WHERE central_bank='CNB' AND url LIKE '%cnb.cz/en/%'")
print(f"Deleted {cur.rowcount} English-URL CNB speeches")
conn.commit()
conn.close()
