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

## 👥 Workflow Collaboratif

Ce projet est conçu pour être travaillé en équipe. Voici comment un ami peut vous rejoindre pour accélérer la segmentation des 604 pages du Mushaf.

### Prérequis pour le collaborateur

Votre ami doit :

1. **Avoir un compte Hugging Face** (gratuit) pour obtenir un token d'accès
2. **Avoir Git et Python 3.10+** installés sur sa machine
3. **Avoir ~6 GB d'espace disque** pour les données

### Étapes d'installation pour le collaborateur

```bash
# 1. Cloner le repository
git clone https://github.com/malekaidoudi/segment-quran.git
cd segment-quran

# 2. Créer l'environnement virtuel
python3.10 -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer le token Hugging Face
cp .env.example .env
# Éditer .env avec son propre HUGGINGFACE_TOKEN
```

### Répartition du travail

Pour éviter les conflits, divisez les pages entre vous :

```
Exemple pour 2 personnes :
• Vous        : pages 1 à 302
• Votre ami   : pages 303 à 604

Exemple pour 3 personnes :
• Personne 1  : pages 1 à 200
• Personne 2  : pages 201 à 400
• Personne 3  : pages 401 à 604
```

> Chaque page génère un fichier JSON dans `data/annotations/` (ex: `page_002.json`).

### Lancer l'application de segmentation

Votre ami peut utiliser l'une des deux interfaces :

**Option A - Application Streamlit (recommandée)** :
```bash
streamlit run src/version_ameliorer.py
```
Interface web accessible sur `http://localhost:8501`. Permet de naviguer entre les pages, ajuster les polygones, corriger les numéros d'ayats et enregistrer les annotations.

**Option B - Application Desktop** :
```bash
python src/desktop_app.py
```
Interface PyQt6 avec thème sombre, raccourcis clavier et vérification de cohérence intégrée.

### Processus de travail

1. **Charger une page** : L'application télécharge automatiquement les images depuis Hugging Face au premier lancement
2. **Segmenter** : L'application détecte automatiquement les ayats via template matching. Le collaborateur n'a qu'à ajuster les polygones si nécessaire
3. **Corriger** : Modifier les numéros de sourate/ayat, ajuster les divisions (hizb), corriger la position des rectangles
4. **Sauvegarder** : Les annotations sont enregistrées dans `data/annotations/page_XXX.json`

### Fusionner le travail de plusieurs personnes

#### Méthode 1 : Via Hugging Face (recommandée)

Quand un collaborateur termine sa plage de pages :

```bash
# Le collaborateur upload ses annotations
python upload_to_hf.py
```

Puis vous téléchargez la dernière version :
```bash
# Supprimer les données locales pour forcer le re-téléchargement
rm -rf data/
python -c "from src.data_manager import ensure_data; ensure_data()"
```

#### Méthode 2 : Via Git + fichiers JSON

Les fichiers d'annotations (`data/annotations/*.json`) sont petits (~1-5 KB chacun). Le collaborateur peut :

```bash
# Envoyer uniquement ses fichiers JSON
rsync -av data/annotations/page_300_*.json user@host:~/segment-quran/data/annotations/
# Ou via cloud (Google Drive, Dropbox, etc.)
```

Vous copiez ensuite ses fichiers dans votre dossier `data/annotations/`.

### Bonnes pratiques collaboratives

- **Communiquer les plages** : Avant de commencer, confirmez qui fait quelles pages
- **Vérifier la cohérence** : L'application `desktop_app.py` vérifie automatiquement la continuité entre les pages (ex: le dernier ayat de la page 302 doit correspondre au premier de la page 303)
- **Ne pas modifier les mêmes fichiers simultanément** : Attendez qu'une personne finisse une page avant de la reprendre
- **Backup réguliers** : Avant de fusionner, gardez une copie de votre dossier `data/annotations/`

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

