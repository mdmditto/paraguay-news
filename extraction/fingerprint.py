import hashlib
import json


def article_hash(article_data: dict) -> str:
    relevant_data = {
        "title": article_data.get("title"),
        "author": article_data.get("author"),
        "body": article_data.get("body"),
    }

    serialized = json.dumps(
        relevant_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()