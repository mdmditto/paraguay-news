import torch
from sentence_transformers import SentenceTransformer

MODEL_NAME = "jinaai/jina-embeddings-v5-text-small"

print("=" * 60)
print("SYSTEM")
print("=" * 60)

print("PyTorch:", torch.__version__)
print("CUDA:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())

if not torch.cuda.is_available():
    raise RuntimeError("CUDA is not available")

print("GPU:", torch.cuda.get_device_name(0))

torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()


# --------------------------------------------------
# Load Jina v5
# --------------------------------------------------

print("\n" + "=" * 60)
print("LOADING JINA V5 SMALL")
print("=" * 60)

model = SentenceTransformer(
    MODEL_NAME,
    trust_remote_code=True,
    device="cuda",
    model_kwargs={
        "dtype": torch.bfloat16,
    },
)

print("Model loaded successfully.")

print(
    "VRAM after loading:",
    round(torch.cuda.memory_allocated() / 1024**3, 2),
    "GB",
)


# --------------------------------------------------
# Test articles
# --------------------------------------------------

texts = [
    """
    La Cámara de Senadores aprobó el proyecto de reforma
    educativa durante la sesión de este miércoles.
    La propuesta continuará ahora su trámite legislativo.
    """,

    """
    El Senado dio aprobación al proyecto de reforma
    educativa luego de una extensa sesión. La iniciativa
    continuará su tratamiento en el Congreso.
    """,

    """
    Olimpia realizó este miércoles su entrenamiento
    pensando en el próximo partido del campeonato
    paraguayo.
    """,
]


# --------------------------------------------------
# Generate embeddings
# --------------------------------------------------

print("\n" + "=" * 60)
print("GENERATING EMBEDDINGS")
print("=" * 60)

with torch.inference_mode():

    embeddings = model.encode(
        texts,
        task="text-matching",
        batch_size=1,
        convert_to_tensor=True,
        normalize_embeddings=True,
    )


# --------------------------------------------------
# Results
# --------------------------------------------------

print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)

print("Shape:", embeddings.shape)
print("Device:", embeddings.device)
print("dtype:", embeddings.dtype)

similarities = model.similarity(
    embeddings,
    embeddings,
)

print("\nSimilarity matrix:")
print(similarities)


# --------------------------------------------------
# Individual similarities
# --------------------------------------------------

print("\nA ↔ B:", round(similarities[0][1].item(), 4))
print("A ↔ C:", round(similarities[0][2].item(), 4))
print("B ↔ C:", round(similarities[1][2].item(), 4))


# --------------------------------------------------
# GPU memory
# --------------------------------------------------

print("\n" + "=" * 60)
print("GPU MEMORY")
print("=" * 60)

print(
    "Current:",
    round(torch.cuda.memory_allocated() / 1024**3, 2),
    "GB",
)

print(
    "Peak:",
    round(torch.cuda.max_memory_allocated() / 1024**3, 2),
    "GB",
)

print(
    "Reserved:",
    round(torch.cuda.memory_reserved() / 1024**3, 2),
    "GB",
)