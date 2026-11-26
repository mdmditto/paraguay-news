
import csv
import sys

from sqlalchemy import text
from database.db import SessionLocal

CSV_PATH = sys.argv[1]

VALID_LABELS = {
    "Colorado",
    "Neutro",
    "Anticolorado",
}

with open(CSV_PATH, newline="", encoding="cp1252") as f:
    rows = list(csv.DictReader(f))

# Validate everything before modifying the database.
updates = []

for row in rows:
    label = row["partidario"].strip()
    source_id = int(row["id"])
    domain = row["domain"].strip()

    if label not in VALID_LABELS:
        raise ValueError(
            f"Invalid classification for source {source_id}: {label}"
        )

    updates.append({
        "id": source_id,
        "domain": domain,
        "partidario": label,
    })

with SessionLocal() as session:
    for item in updates:
        result = session.execute(
            text("""
                UPDATE sources
                SET partidario = :partidario
                WHERE id = :id
                  AND domain = :domain
            """),
            item,
        )

        if result.rowcount != 1:
            raise ValueError(
                f"Source mismatch: {item['id']} / {item['domain']}"
            )

    session.commit()

print(f"Updated {len(updates)} sources.")
