from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sqlalchemy import text

from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize
from sklearn.decomposition import PCA
from sklearn.metrics import (
    silhouette_score,
    silhouette_samples,
    pairwise_distances,
    adjusted_rand_score
)

from scipy.cluster.hierarchy import linkage, dendrogram

from database.db import SessionLocal


RANDOM_STATE = 42
N_CLUSTERS = 2
MIN_ARTICLES = 30

BASE_DIR = Path(__file__).resolve().parent

RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = (
    BASE_DIR
    / "models"
    / "political_classifier.joblib"
)


def load_embeddings():

    artifact = joblib.load(MODEL_PATH)

    query = text("""
        SELECT
            a.article_id,
            a.source_id,
            a.source,
            a.published_at,
            a.political_probability,
            e.embedding::text AS embedding

        FROM political_orientation_dataset a

        JOIN article_embeddings e
            ON a.article_id = e.article_id

        WHERE e.model = :model
          AND e.task = :task
          AND e.dimensions = :dimensions
          AND e.embedding IS NOT NULL
          AND a.source != 'Amambay News'
          AND a.source != 'Amambay Ahora'
          AND a.source != 'Ahora CDE'
          AND a.source != 'Oviedo Press'
          AND a.source != 'Concepción al Día'
          AND a.source != 'Itapúa en Noticias'
          AND a.source != 'QAP Chaco News'
          AND a.source != 'Pedro Juan Digital'
          AND a.source != 'Red Digital San Pedro'
          AND a.source != 'La Clave'
          AND a.source != 'San Lorenzo Hoy'
          AND a.source != 'Primera Plana'
          AND a.source != 'TN Press'
        ORDER BY a.source_id, a.article_id
    """)

    with SessionLocal() as session:

        result = session.execute(
            query,
            {
                "model": artifact["embedding_model"],
                "task": artifact["task"],
                "dimensions": artifact["dimensions"]
            }
        )

        df = pd.DataFrame(
            result.mappings().all()
        )

    if df.empty:
        raise ValueError("No embeddings retrieved.")

    assert df["article_id"].is_unique

    return df


def aggregate_embeddings(df):

    source_records = []
    source_vectors = []

    for source_id, group in df.groupby("source_id"):

        if len(group) < MIN_ARTICLES:
            continue

        X = np.stack([
            np.fromstring(
                embedding.strip("[]"),
                sep=",",
                dtype=np.float32
            )
            for embedding in group["embedding"]
        ])

        assert X.shape[1] == 1024
        assert np.isfinite(X).all()

        # Normalize individual article embeddings
        X = normalize(X, norm="l2")

        # Calculate mean embedding
        centroid = X.mean(axis=0)

        source_vectors.append(centroid)

        source_records.append({
            "source_id": source_id,
            "source": group["source"].iloc[0],
            "political_articles": len(group)
        })

    sources = pd.DataFrame(source_records)

    X_sources = np.stack(source_vectors)

    # Normalize news outlet embeddings
    X_sources = normalize(
        X_sources,
        norm="l2"
    )

    return sources, X_sources


def plot_clusters(sources, X):

    pca = PCA(n_components=2)

    coordinates = pca.fit_transform(X)

    sources["PC1"] = coordinates[:, 0]
    sources["PC2"] = coordinates[:, 1]

    fig, ax = plt.subplots(figsize=(14, 10))

    for cluster in sorted(sources["cluster"].unique()):

        subset = sources[
            sources["cluster"] == cluster
        ]

        ax.scatter(
            subset["PC1"],
            subset["PC2"],
            s=100,
            alpha=0.85,
            label=f"Cluster {cluster}"
        )

        for _, row in subset.iterrows():

            ax.annotate(
                row["source"],
                (row["PC1"], row["PC2"]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8
            )

    explained = pca.explained_variance_ratio_

    ax.set_xlabel(
        f"PC1 ({explained[0]:.1%} explained variance)"
    )

    ax.set_ylabel(
        f"PC2 ({explained[1]:.1%} explained variance)"
    )

    ax.set_title(
        "Dubito: Political Clustering of News Outlets"
    )

    ax.legend()
    ax.grid(alpha=0.2)

    plt.tight_layout()

    plt.savefig(
        RESULTS_DIR / "news_clusters_pca.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)

    print("\nPCA explained variance:")
    print(explained)

    return sources


def plot_dendrogram(sources, X):

    Z = linkage(
        X,
        method="average",
        metric="cosine"
    )

    fig, ax = plt.subplots(figsize=(16, 10))

    dendrogram(
        Z,
        labels=sources["source"].tolist(),
        orientation="right",
        leaf_font_size=10,
        ax=ax
    )

    ax.set_title(
        "Political Similarity Between News Outlets"
    )

    ax.set_xlabel("Cosine distance")

    plt.tight_layout()

    plt.savefig(
        RESULTS_DIR / "news_dendrogram.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


def plot_similarity_matrix(sources, X):

    similarity = 1 - pairwise_distances(
        X,
        metric="cosine"
    )

    order = np.argsort(
        sources["cluster"].to_numpy(),
        kind="stable"
    )

    similarity = similarity[np.ix_(order, order)]

    names = sources.iloc[order]["source"].tolist()

    fig, ax = plt.subplots(figsize=(14, 12))

    im = ax.imshow(
        similarity,
        cmap="viridis"
    )

    ax.set_xticks(range(len(names)))
    ax.set_yticks(range(len(names)))

    ax.set_xticklabels(
        names,
        rotation=90,
        fontsize=8
    )

    ax.set_yticklabels(
        names,
        fontsize=8
    )

    fig.colorbar(
        im,
        ax=ax,
        label="Cosine similarity"
    )

    ax.set_title(
        "Political Similarity Matrix of News Outlets"
    )

    plt.tight_layout()

    plt.savefig(
        RESULTS_DIR / "news_similarity_matrix.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)

    pd.DataFrame(
        similarity,
        index=names,
        columns=names
    ).to_csv(
        RESULTS_DIR / "news_similarity_matrix.csv"
    )


def main():

    print("Loading political article embeddings...")

    df = load_embeddings()

    print("Articles:", len(df))
    print("Sources:", df["source_id"].nunique())

    print("\nAggregating embeddings by source...")

    sources, X = aggregate_embeddings(df)

    print("Source embedding matrix:", X.shape)

    model = KMeans(
        n_clusters=N_CLUSTERS,
        random_state=RANDOM_STATE,
        n_init=100,
        max_iter=1000
    )

    sources["cluster"] = model.fit_predict(X)

    score = silhouette_score(
        X,
        sources["cluster"]
    )

    sources["silhouette"] = silhouette_samples(
        X,
        sources["cluster"]
    )

    distances = model.transform(X)

    sources["distance_to_centroid"] = distances[
        np.arange(len(sources)),
        sources["cluster"].to_numpy()
    ]

    print("\n=== K-MEANS RESULTS ===")

    print("K:", N_CLUSTERS)
    print("Inertia:", round(model.inertia_, 6))
    print("Silhouette score:", round(score, 4))

    for cluster in sorted(sources["cluster"].unique()):

        subset = sources[
            sources["cluster"] == cluster
        ].sort_values(
            "distance_to_centroid"
        )

        print(f"\n=== CLUSTER {cluster} ===")
        print("Sources:", len(subset))

        print(
            subset[[
                "source",
                "political_articles",
                "silhouette",
                "distance_to_centroid"
            ]].to_string(index=False)
        )

    # Check sensitivity to random initialization
    stability = []

    for seed in range(20):

        alternative = KMeans(
            n_clusters=N_CLUSTERS,
            n_init=20,
            random_state=seed
        ).fit_predict(X)

        stability.append(
            adjusted_rand_score(
                sources["cluster"],
                alternative
            )
        )

    print("\nMean initialization stability:")
    print(round(np.mean(stability), 4))

    # Generate visualizations
    sources = plot_clusters(sources, X)

    plot_dendrogram(sources, X)

    plot_similarity_matrix(sources, X)

    # Export results
    sources.sort_values([
        "cluster",
        "distance_to_centroid"
    ]).to_csv(
        RESULTS_DIR / "news_source_clusters.csv",
        index=False
    )

    np.save(
        RESULTS_DIR / "news_source_embeddings.npy",
        X
    )

    sources.to_csv(
        RESULTS_DIR / "news_source_embedding_index.csv",
        index=False
    )

    joblib.dump(
        model,
        RESULTS_DIR / "news_source_kmeans.joblib"
    )

    print("\nResults saved to:")
    print(RESULTS_DIR)


if __name__ == "__main__":
    main()