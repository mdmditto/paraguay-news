from sqlalchemy import text

from database.db import engine


def main():

    with engine.connect() as connection:

        result = connection.execute(
            text("SELECT version();")
        )

        version = result.scalar()

        print("Connection successful!")
        print(version)


if __name__ == "__main__":
    main()
