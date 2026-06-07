# 📖 Mushaf Qalun - Détecteur d'Ayats

Pipeline hybride pour la détection automatique des ayats du Coran dans un Mushaf Qalun (images PNG).

## 🎯 Objectif

À partir de pages du Mushaf en PNG et d'un template de marqueur d'ayah, détecter automatiquement tous les ayats et générer un fichier JSON avec leurs positions exactes.

## 🧠 Pipeline Hybride

```
┌─────────────────┐     ┌─────────────┐     ┌─────────────┐
│  Images PNG     │────→│  Template   │────→│   NMS       │
│  + Marker.png   │     │  Matching   │     │  (doublons) │
└─────────────────┘     └─────────────┘     └──────┬──────┘
                                                   │
                          ┌─────────────────┐      │
                          │   YOLOv8        │←─────┘
                          │   (filtre FP)   │
                          │   (optionnel)   │
                          └────────┬────────┘
                                   │
                          ┌────────▼────────┐
                          │   Tri spatial   │
                          │  Y↑, X→ (arabe) │
                          └────────┬────────┘
                                   │
                          ┌────────▼────────┐
                          │  Alignement     │
                          │  avec CSV       │
                          └────────┬────────┘
                                   │
                          ┌────────▼────────┐
                          │  Export JSON    │
                          │  + Visualisation│
                          └─────────────────┘
```

## 📁 Structure du Projet

```
segment-quran/
├── data/                      # Données (téléchargées auto depuis Hugging Face)
│   ├── images/                # Pages du Mushaf (PNG)
│   ├── audio/                 # Fichiers audio découpés
│   ├── annotations/           # Annotations JSON par page
│   ├── ayats.csv              # 6236 ayats avec métadonnées
│   ├── name_sourat.csv        # Noms des sourates
│   ├── sommaire.csv           # Sommaire
│   ├── marker.png             # Template du marqueur d'ayah
│   ├── entete.png             # Image d'en-tête
│   └── qalun.pdf              # PDF du Mushaf
├── src/
│   ├── audio_splitter.py      # Découpage audio
│   ├── ayah_segmenter_final.py # Application Streamlit
│   ├── desktop_app.py         # Application desktop
│   ├── desktop_app_resp.py    # Version responsive
│   ├── version_ameliorer.py   # Version améliorée
│   └── data_manager.py        # Gestion des données HF
├── requirements.txt
├── .env.example               # Exemple de variables d'environnement
├── .gitignore
└── README.md
```

> **Note :** Le dossier `data/` n'est pas inclus dans le repository Git (trop volumineux). Les données sont téléchargées automatiquement depuis Hugging Face au premier lancement.

## ⚙️ Installation

### 1. Cloner le repository

```bash
git clone https://github.com/malekaidoudi/segment-quran.git
cd segment-quran
```

### 2. Créer un environnement virtuel (recommandé)

```bash
python3.10 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer Hugging Face

Créez un fichier `.env` à la racine du projet :

```bash
cp .env.example .env
```

Éditez `.env` et remplacez `hf_xxx` par votre token Hugging Face :

```bash
HUGGINGFACE_TOKEN=hf_votre_token_ici
HF_DATASET_REPO=malekaidoudi/segment-quran-data
```

> Obtenez votre token sur [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

### 5. Lancer une application

```bash
# Application Streamlit
streamlit run src/ayah_segmenter_final.py

# Application desktop
python src/desktop_app.py

# Découpage audio
python src/audio_splitter.py
```

> **Note :** Au premier lancement, les données (~6 GB) seront téléchargées automatiquement depuis Hugging Face.

## 🚀 Utilisation

### Application Streamlit (Segmentation des Ayahs)

```bash
streamlit run src/ayah_segmenter_final.py
```

Permet de :
- Naviguer entre les pages du Mushaf
- Segmenter et annoter les ayahs
- Visualiser les polygones de détection
- Afficher les numéros d'ayats

### Application Desktop

```bash
python src/desktop_app.py
```

Interface desktop pour la segmentation et l'annotation.

### Découpage Audio

```bash
python src/audio_splitter.py
```

Découpe les fichiers audio selon les annotations.

## � Données sur Hugging Face

Le dossier `data/` (~6 GB) est stocké sur Hugging Face pour éviter de surcharger le repository Git.

### Téléchargement automatique

Les applications téléchargent automatiquement les données au premier lancement via `data_manager.py`.

### Uploader des données (pour les mainteneurs)

Si vous modifiez les données localement et souhaitez mettre à jour le dataset Hugging Face :

```bash
python upload_to_hf.py
```

> Nécessite le token Hugging Face configuré dans `.env`.

## 🐛 Dépannage

### Erreur : "HUGGINGFACE_TOKEN manquante"
Créez le fichier `.env` à la racine du projet :
```bash
cp .env.example .env
```
Puis éditez-le avec votre token.

### Erreur : "Données non trouvées"
Vérifiez votre connexion internet et le token Hugging Face. Les données se téléchargent automatiquement depuis Hugging Face.

## 🤝 Contribution

1. Fork le projet
2. Créez une branche (`git checkout -b feature/xyz`)
3. Committez vos changements (`git commit -am 'Add feature'`)
4. Push sur la branche (`git push origin feature/xyz`)
5. Ouvrez une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails.

## 🙏 Remerciements

- Ultralytics pour YOLOv8
- OpenCV pour le template matching
- La communauté Python pour les outils exceptionnels

## 📧 Contact

Pour questions ou suggestions : [votre-email@example.com]

---

**Note :** Ce projet est destiné à faciliter l'étude du Coran. Respectez les droits d'auteur des images du Mushaf utilisées.

