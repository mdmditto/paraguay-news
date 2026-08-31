from sqlalchemy import select

from database.db import SessionLocal
from database.models import Source


SOURCE_METADATA = {
    "abc.com.py": {
        "source_type": "newspaper",
        "institutional_class": "private",
        "language": "es",
        "country": "PY",
    },

    "ultimahora.com": {
        "source_type": "newspaper",
        "institutional_class": "private",
        "language": "es",
        "country": "PY",
    },

    "lanacion.com.py": {
        "source_type": "newspaper",
        "institutional_class": "private",
        "language": "es",
        "country": "PY",
    },

    "hoy.com.py": {
        "source_type": "digital_news",
        "institutional_class": "private",
        "language": "es",
        "country": "PY",
    },

    "npy.com.py": {
        "source_type": "television",
        "institutional_class": "private",
        "language": "es",
        "country": "PY",
    },

    "unicanal.com.py": {
        "source_type": "television",
        "institutional_class": "private",
        "language": "es",
        "country": "PY",
    },

    "ip.gov.py": {
        "source_type": "government_agency",
        "institutional_class": "government",
        "language": "es",
        "country": "PY",
    },

    "monumental.com.py": {
        "source_type": "radio",
        "institutional_class": "private",
        "language": "es",
        "country": "PY",
    },

    "5dias.com.py": {
        "source_type": "business_media",
        "institutional_class": "private",
        "language": "es",
        "country": "PY",
    },

    "telefuturo.com.py": {
        "source_type": "television",
        "institutional_class": "private",
        "language": "es",
        "country": "PY",
    },
}


def main():
    with SessionLocal() as db:

        for domain, metadata in SOURCE_METADATA.items():

            source = db.scalar(
                select(Source).where(
                    Source.domain == domain
                )
            )

            if source is None:
                print(
                    f"Source not found: {domain}"
                )
                continue

            for field, value in metadata.items():
                setattr(
                    source,
                    field,
                    value,
                )

            print(
                f"Updated: {source.name}"
            )

        db.commit()


if __name__ == "__main__":
    main()
