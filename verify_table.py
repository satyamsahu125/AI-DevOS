import sqlite3
conn = sqlite3.connect('F:/AI-DevOS3/backend/data/memory.sqlite')
cursor = conn.cursor()
cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="workflow_events"')
result = cursor.fetchone()
if result:
    print(result[0])
else:
    print("Table not found")