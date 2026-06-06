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
mushaf-qalun-detector/
├── data/
│   ├── images/          # Pages du Mushaf (PNG)
│   ├── ayats.csv      # 6236 ayats avec métadonnées
│   └── marker.png     # Template du marqueur d'ayah
├── models/
│   └── best.pt        # Modèle YOLOv8 (optionnel)
├── src/
│   ├── template_detect.py   # Template Matching + NMS
│   ├── yolo_filter.py       # Filtrage YOLOv8
│   ├── align_ayahs.py       # Alignement avec CSV
│   └── main.py              # Pipeline principal
├── web/
│   ├── index.html      # Interface web
│   ├── viewer.js       # Visualisation interactive
│   └── style.css       # Styles
├── output/
│   ├── result.json     # Résultats finaux
│   └── debug_*.png     # Images debug (optionnel)
├── requirements.txt
└── README.md
```

## ⚙️ Installation

### 1. Cloner le repository

```bash
git clone <repository-url>
cd mushaf-qalun-detector
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

### 4. Vérifier l'installation

```bash
python src/main.py --help
```

## 🚀 Utilisation

### Traiter une seule page

```bash
python src/main.py --image data/images/page_001.png --debug
```

### Traiter toutes les pages

```bash
python src/main.py --all --images-dir data/images --debug
```

### Options avancées

```bash
# Seuil personnalisé pour template matching
python src/main.py --all --threshold 0.8

# Sans YOLO (template matching uniquement)
python src/main.py --all --no-yolo

# Seuil YOLO personnalisé
python src/main.py --all --yolo-conf 0.7

# Pattern de fichiers différent
python src/main.py --all --pattern "*.jpg"
```

### Visualiser les résultats

Ouvrez `web/index.html` dans un navigateur web pour visualiser les résultats avec overlay interactif.

## 📊 Format du JSON de sortie

```json
{
  "metadata": {
    "total_ayahs": 6236,
    "matched_ayahs": 6150,
    "total_pages": 604,
    "detection_rate": 0.986
  },
  "ayahs": [
    {
      "surah": 1,
      "ayah": 1,
      "page": 1,
      "x": 120,
      "y": 250,
      "w": 32,
      "h": 32,
      "confidence": 0.95,
      "polygon": [[120, 250], [152, 250], [152, 282], [120, 282]],
      "matched": true
    }
  ]
}
```

## 📝 Format du CSV (ayats.csv)

```csv
id,surah,ayah,page
1,1,1,1
2,1,2,1
...
6236,114,6,604
```

## 🔧 Configuration

### Paramètres modifiables

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| `--threshold` | Seuil template matching | 0.7 |
| `--yolo-conf` | Seuil confiance YOLO | 0.5 |
| `--multi-scale` | Multi-échelle template | true |
| `--overlap-threshold` | Seuil NMS | 0.3 |

### Environnement

Créez un fichier `.env` pour les variables d'environnement :

```bash
LOG_LEVEL=INFO
CUDA_VISIBLE_DEVICES=0  # Pour GPU
```

## 🌐 Interface Web

L'interface web permet de :
- Naviguer entre les pages du Mushaf
- Visualiser les polygones de détection
- Afficher les numéros d'ayats
- Ajuster l'opacité des overlays
- Voir les détails de chaque ayah au survol

**Navigation clavier :**
- `←` : Page précédente
- `→` : Page suivante

## 📸 Mode Debug

Activez `--debug` pour générer des images annotées :

```bash
python src/main.py --all --debug
```

Cela crée des images avec :
- Rectangles autour des détections
- Scores de confiance
- Numéros de détection

## 🧪 Tests

```bash
# Tests unitaires
pytest tests/

# Vérifier le style
flake8 src/
black src/ --check
```

## 🐛 Dépannage

### Erreur : "Marqueur non trouvé"
Vérifiez que `data/marker.png` existe et correspond au marqueur d'ayah de votre Mushaf.

### Erreur : "YOLO non disponible"
YOLOv8 est optionnel. Le pipeline fonctionne avec le template matching uniquement.
Pour installer YOLO :
```bash
pip install ultralytics
```

### Détections manquantes
- Réduisez `--threshold` (ex: 0.6)
- Activez `--multi-scale`
- Vérifiez que le marker.png correspond bien

### Faux positifs
- Augmentez `--threshold` (ex: 0.8)
- Utilisez `--yolo-conf` plus élevé
- Vérifiez avec `--debug`

## 📚 Architecture du Code

### `template_detect.py`
- `Detection` : Classe de données pour une détection
- `match_template()` : Template matching avec OpenCV
- `non_max_suppression()` : Élimination des doublons
- `detect_markers()` : Pipeline de détection complet

### `yolo_filter.py`
- `YoloFilter` : Classe pour filtrer avec YOLOv8
- `heuristic_filter()` : Filtre fallback sans YOLO
- `validate_region()` : Validation d'une région spécifique

### `align_ayahs.py`
- `AyahAligner` : Aligne les détections avec le CSV
- `sort_detections()` : Tri Y croissant, X décroissant
- `export_to_json()` : Export des résultats

### `main.py`
- `QuranAyahDetector` : Pipeline complet
- Gestion des arguments CLI
- Coordination des étapes

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

