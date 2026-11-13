import json
import time

wall, monotonic = time.time(), time.monotonic()
rows = []
for _ in range(45):
    time.sleep(1)
    new_wall, new_monotonic = time.time(), time.monotonic()
    rows.append({"wall": new_wall-wall, "monotonic": new_monotonic-monotonic, "at": new_wall})
    wall, monotonic = new_wall, new_monotonic
print(json.dumps({"samples": len(rows), "anomalies": [row for row in rows if abs(row["wall"]-row["monotonic"])>.2], "max_monotonic": max(row["monotonic"] for row in rows)}))