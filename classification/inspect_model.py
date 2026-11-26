import joblib

from pathlib import Path

MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "political_classifier.joblib"
)

artifact = joblib.load(MODEL_PATH)

model = artifact["model"]

print("=== MODEL INFORMATION ===")

for key, value in artifact.items():
    if key != "model":
        print(f"{key}: {value}")

print("\n=== MODEL PARAMETERS ===")
print(model.get_params())

print("\n=== TRAINED MODEL ===")
print("Classes:", model.classes_)
print("Number of features:", model.n_features_in_)
print("Coefficients shape:", model.coef_.shape)
print("Intercept:", model.intercept_)
print("Iterations:", model.n_iter_)