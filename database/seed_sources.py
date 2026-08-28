from sqlalchemy import select

from database.db import SessionLocal
from database.models import Source


SOURCES = [
    {
        "name": "ABC Color",
        "domain": "abc.com.py",
    },
    {
        "name": "Última Hora",
        "domain": "ultimahora.com",
    },
    {
        "name": "La Nación",
        "domain": "lanacion.com.py",
    },
    {
        "name": "HOY",
        "domain": "hoy.com.py",
    },
    {
        "name": "NPY",
        "domain": "npy.com.py",
    },
    {   "name": "UNICANAL",
        "domain": "unicanal.com.py",
    },
    {   "name": "Agencia IP",
        "domain": "ip.gov.py"
    },
    {
        "name": "Monumental",
        "domain": "monumental.com.py",
    },
    {
        "name": "5Días",
        "domain": "5dias.com.py",
    },
    {
        "name": "Telefuturo",
        "domain": "telefuturo.com.py",
    }
]


def main():

    with SessionLocal() as db:

        for data in SOURCES:

            existing = db.scalar(
                select(Source).where(
                    Source.domain
                    == data["domain"]
                )
            )

            if existing:
                print(
                    f"Already exists: "
                    f"{data['name']}"
                )
                continue

            source = Source(**data)

            db.add(source)

            print(
                f"Adding: "
                f"{data['name']}"
            )

        db.commit()

    print("Done.")


if __name__ == "__main__":
    main()
