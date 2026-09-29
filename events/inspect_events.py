import pandas as pd

events = pd.read_csv(
    "events/output/simulated_events.csv"
)

articles = pd.read_csv(
    "events/output/simulated_event_articles.csv"
)

for _, event in events.head(20).iterrows():

    event_id = event["event_id"]

    members = articles[
        articles["event_id"] == event_id
    ]

    print("\n" + "=" * 100)
    print(
        f"EVENT {event_id} "
        f"({len(members)} articles)"
    )
    print("=" * 100)

    for _, article in members.iterrows():

        probability = article[
            "selected_event_probability"
        ]

        if pd.isna(probability):
            probability_text = "SEED"
        else:
            probability_text = f"{probability:.4f}"

        print(
            f"[{article['source']}] "
            f"p={probability_text} | "
            f"{article['title']}"
        )
