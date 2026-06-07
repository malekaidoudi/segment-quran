"""
Data Manager - Gestion des données depuis Hugging Face
========================================================
Télécharge automatiquement le dataset depuis Hugging Face
si le dossier data/ n'est pas présent localement.
"""

import os
import sys
from pathlib import Path

# Charger les variables d'environnement depuis .env
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"

# Repository Hugging Face (dataset)
HF_DATASET_REPO = os.getenv("HF_DATASET_REPO", "malekaidoudi/segment-quran-data")


def _ensure_huggingface_hub():
    """Vérifie que huggingface_hub est installé."""
    try:
        from huggingface_hub import snapshot_download
        return snapshot_download
    except ImportError:
        print("[ERREUR] huggingface_hub n'est pas installé.")
        print("         pip install huggingface_hub")
        sys.exit(1)


def ensure_data() -> Path:
    """
    S'assure que le dossier data/ existe.
    Si non, télécharge le dataset depuis Hugging Face.
    """
    # Vérifier que les données essentielles existent (images et annotations)
    images_dir = DATA_DIR / "images"
    annotations_dir = DATA_DIR / "annotations"
    if (images_dir.exists() and any(images_dir.iterdir()) and
            annotations_dir.exists() and any(annotations_dir.iterdir())):
        return DATA_DIR

    snapshot_download = _ensure_huggingface_hub()

    token = os.getenv("HUGGINGFACE_TOKEN")
    if not token:
        print("[ERREUR] Variable d'environnement HUGGINGFACE_TOKEN manquante.")
        print("         Créez un fichier .env à la racine du projet:")
        print("         HUGGINGFACE_TOKEN=hf_xxx")
        sys.exit(1)

    print("=" * 60)
    print("📦 Données non trouvées localement.")
    print(f"🔄 Téléchargement depuis Hugging Face: {HF_DATASET_REPO}")
    print("=" * 60)

    os.makedirs(DATA_DIR, exist_ok=True)

    snapshot_download(
        repo_id=HF_DATASET_REPO,
        repo_type="dataset",
        token=token,
        local_dir=str(DATA_DIR),
        local_dir_use_symlinks=False,
    )

    print("✅ Données téléchargées avec succès.")
    return DATA_DIR


def get_path(*parts: str) -> str:
    """Retourne un chemin absolu dans le dossier data."""
    ensure_data()
    return str(DATA_DIR.joinpath(*parts))


def data_exists() -> bool:
    """Vérifie si le dossier data existe et contient des fichiers."""
    return DATA_DIR.exists() and any(DATA_DIR.iterdir())


def sync_data() -> Path:
    """
    Force la synchronisation complète avec Hugging Face.
    Télécharge les fichiers manquants ou modifiés depuis le dataset.
    """
    snapshot_download = _ensure_huggingface_hub()

    token = os.getenv("HUGGINGFACE_TOKEN")
    if not token:
        print("[ERREUR] Variable d'environnement HUGGINGFACE_TOKEN manquante.")
        sys.exit(1)

    print("=" * 60)
    print("🔄 Synchronisation avec Hugging Face...")
    print(f"   Repo: {HF_DATASET_REPO}")
    print("=" * 60)

    os.makedirs(DATA_DIR, exist_ok=True)

    snapshot_download(
        repo_id=HF_DATASET_REPO,
        repo_type="dataset",
        token=token,
        local_dir=str(DATA_DIR),
        local_dir_use_symlinks=False,
    )

    print("✅ Synchronisation terminée.")
    return DATA_DIR


def get_hf_data_info() -> dict:
    """
    Retourne un dict avec les infos du dataset HF (fichiers, tailles, etc.)
    """
    try:
        from huggingface_hub import list_repo_files, hf_api
        token = os.getenv("HUGGINGFACE_TOKEN")
        if not token:
            return {}
        files = list_repo_files(
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
            token=token,
        )
        # Grouper par dossier audio/output/XXX
        surah_files = {}
        for f in files:
            if "audio/output/" in f:
                parts = f.split("/")
                try:
                    idx = parts.index("output")
                    folder = parts[idx + 1] if idx + 1 < len(parts) else ""
                    if folder.isdigit():
                        surah_files.setdefault(int(folder), []).append(f)
                except (ValueError, IndexError):
                    pass
        return surah_files
    except Exception as e:
        print(f"⚠️ Erreur lecture infos HF: {e}")
        return {}


# Auto-téléchargement au premier import si lancé en CLI
if __name__ == "__main__":
    ensure_data()
