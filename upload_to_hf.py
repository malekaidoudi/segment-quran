#!/usr/bin/env python3
"""
Uploader le dossier data/ vers Hugging Face
============================================
Usage:
    export HUGGINGFACE_TOKEN=hf_xxx
    python upload_to_hf.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi, create_repo

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# Configuration
DATA_DIR = PROJECT_ROOT / "data"
HF_DATASET_REPO = os.getenv("HF_DATASET_REPO", "malekaidoudi/segment-quran-data")
TOKEN = os.getenv("HUGGINGFACE_TOKEN")


def main():
    if not TOKEN:
        print("[ERREUR] Définissez HUGGINGFACE_TOKEN")
        sys.exit(1)

    if not DATA_DIR.exists():
        print(f"[ERREUR] Dossier non trouvé: {DATA_DIR}")
        sys.exit(1)

    print(f"📤 Upload vers Hugging Face: {HF_DATASET_REPO}")
    print(f"📁 Source: {DATA_DIR}")

    api = HfApi(token=TOKEN)

    # Créer le repo s'il n'existe pas
    try:
        create_repo(
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
            token=TOKEN,
            exist_ok=True,
            private=False,
        )
        print("✅ Repo créé (ou déjà existant)")
    except Exception as e:
        print(f"⚠️ Erreur création repo: {e}")

    # Upload du contenu
    api.upload_folder(
        folder_path=str(DATA_DIR),
        repo_id=HF_DATASET_REPO,
        repo_type="dataset",
        token=TOKEN,
    )

    print("✅ Upload terminé avec succès!")
    print(f"🔗 URL: https://huggingface.co/datasets/{HF_DATASET_REPO}")


if __name__ == "__main__":
    main()
