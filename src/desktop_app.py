#!/usr/bin/env python3
"""
Quran Ayat Editor - Professional Desktop Application
Clean, modern interface for Quran page annotation
"""

import sys
import os
import json
import copy
import re
import hashlib
import cv2
import numpy as np
import pandas as pd
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QListWidget,
    QSplitter, QScrollArea, QGroupBox, QMessageBox, QToolBar,
    QLineEdit, QSlider, QSizePolicy, QToolButton, QButtonGroup,
    QTreeWidget, QTreeWidgetItem, QCheckBox, QHeaderView
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import (
    QPixmap, QImage, QAction, QIcon, QKeySequence, QShortcut,
    QMouseEvent, QColor, QPalette
)

import data_manager

try:
    from huggingface_hub import HfApi, upload_folder
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

# =============================================================================
# CONFIGURATION
# =============================================================================
class Config:
    _BASE = str(data_manager.DATA_DIR)
    IMAGE_DIR = os.path.join(_BASE, "images")
    JSON_DIR = os.path.join(_BASE, "annotations")
    CSV_PATH = os.path.join(_BASE, "name_sourat.csv")
    CSV_SOMMAIRE = os.path.join(_BASE, "sommaire.csv")
    MARKER_PATH = os.path.join(_BASE, "marker.png")
    HEADER_PATH = os.path.join(_BASE, "entete.png")
    
    # Detection defaults - selon parité de la page
    # Page paire: marge G 385, marge D 190
    # Page impaire: marge G 200, marge D 350
    PADDING_LEFT_EVEN = 385
    PADDING_RIGHT_EVEN = 190
    PADDING_LEFT_ODD = 200
    PADDING_RIGHT_ODD = 350
    
    START_Y = 350
    LINE_HEIGHT = 105
    INTER_HEIGHT = 32
    THRESHOLD = 0.35

# Divisions pour le hizb
DIVISIONS = ["start", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8"]


def _load_app_config():
    """Charge la configuration externe si elle existe."""
    config_path = Path(__file__).resolve().parent.parent / "data" / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            # Templates
            tpl = cfg.get("template_paths", {})
            if tpl.get("entete") and Path(tpl["entete"]).exists():
                Config.HEADER_PATH = str(Path(tpl["entete"]).resolve())
            if tpl.get("marker") and Path(tpl["marker"]).exists():
                Config.MARKER_PATH = str(Path(tpl["marker"]).resolve())

            # Détection
            dp = cfg.get("detection_params", {})
            if "threshold" in dp:
                Config.THRESHOLD = dp["threshold"]
            if "padding_left_even" in dp:
                Config.PADDING_LEFT_EVEN = dp["padding_left_even"]
            if "padding_right_even" in dp:
                Config.PADDING_RIGHT_EVEN = dp["padding_right_even"]
            if "padding_left_odd" in dp:
                Config.PADDING_LEFT_ODD = dp["padding_left_odd"]
            if "padding_right_odd" in dp:
                Config.PADDING_RIGHT_ODD = dp["padding_right_odd"]
            if "start_y" in dp:
                Config.START_Y = dp["start_y"]
            if "line_height" in dp:
                Config.LINE_HEIGHT = dp["line_height"]
            if "inter_height" in dp:
                Config.INTER_HEIGHT = dp["inter_height"]
        except Exception:
            pass


_load_app_config()

# Base de données des sourates (globale pour le moteur de détection)
SURAH_DB = {}

# Sommaire: {surah_num: {"page": int, "total_ayats": int, "nom": str}}
SOMMAIRE_DB = {}


# =============================================================================
# STYLES - Dark Professional Theme
# =============================================================================
DARK_STYLE = """
QMainWindow {
    background-color: #1e1e1e;
}
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: "Helvetica Neue", Helvetica, Arial;
    font-size: 13px;
}
QGroupBox {
    font-weight: 600;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    background-color: #252526;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #0d9488;
}
QPushButton {
    background-color: #333333;
    color: #e0e0e0;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px 12px;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #404040;
    border-color: #0d9488;
}
QPushButton:pressed {
    background-color: #0d9488;
    color: white;
}
QPushButton:disabled {
    background-color: #2a2a2a;
    color: #666666;
}
QPushButton#primary {
    background-color: #0d9488;
    color: white;
    font-weight: 600;
}
QPushButton#primary:hover {
    background-color: #0f766e;
}
QPushButton#danger {
    background-color: #dc2626;
    color: white;
}
QPushButton#danger:hover {
    background-color: #b91c1c;
}
QSpinBox, QComboBox, QLineEdit {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}
QSpinBox:focus, QComboBox:focus, QLineEdit:focus {
    border-color: #0d9488;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #888;
    margin-right: 8px;
}
QListWidget {
    background-color: #252526;
    color: #e0e0e0;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    padding: 8px 12px;
    border-radius: 4px;
    margin: 2px 0;
}
QListWidget::item:selected {
    background-color: #0d9488;
    color: white;
}
QListWidget::item:hover:!selected {
    background-color: #333333;
}
QTreeWidget {
    background-color: #252526;
    color: #e0e0e0;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}
QTreeWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
    margin: 1px 0;
}
QTreeWidget::item:selected {
    background-color: #0d9488;
    color: white;
}
QTreeWidget::item:hover:!selected {
    background-color: #333333;
}
QTreeWidget::branch {
    background-color: transparent;
}
QTreeWidget::branch:has-children:closed {
    image: url(none);
    border-image: none;
}
QTreeWidget::branch:has-children:open {
    image: url(none);
    border-image: none;
}
QScrollArea {
    border: none;
    background-color: #1a1a1a;
}
QScrollBar:vertical {
    background-color: #1e1e1e;
    width: 12px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background-color: #444444;
    border-radius: 6px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #555555;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QStatusBar {
    background-color: #0d9488;
    color: white;
    font-weight: 500;
}
QToolBar {
    background-color: #252526;
    border: none;
    padding: 4px;
    spacing: 4px;
}
QLabel#sectionTitle {
    color: #0d9488;
    font-weight: 600;
    font-size: 12px;
    padding: 4px 0;
}
QLabel#info {
    color: #888888;
    font-size: 11px;
}
QSplitter::handle {
    background-color: #333333;
}
QSplitter::handle:horizontal {
    width: 2px;
}
"""


# =============================================================================
# DATA FUNCTIONS
# =============================================================================
def load_surah_database():
    """Load surah names from CSV - format identique à l'app web."""
    global SURAH_DB
    if os.path.exists(Config.CSV_PATH):
        try:
            df = pd.read_csv(Config.CSV_PATH)
            SURAH_DB = df.set_index('number')['nameAr'].to_dict()
            return SURAH_DB
        except Exception as e:
            print(f"Error loading surah database: {e}")
    SURAH_DB = {i: f"Sourate {i}" for i in range(1, 115)}
    return SURAH_DB


def load_sommaire_database():
    """Load sommaire from CSV - pour vérification des sourates."""
    global SOMMAIRE_DB
    if os.path.exists(Config.CSV_SOMMAIRE):
        try:
            df = pd.read_csv(Config.CSV_SOMMAIRE)
            for _, row in df.iterrows():
                SOMMAIRE_DB[int(row['Sourate_Num'])] = {
                    "page": int(row['Page']),
                    "total_ayats": int(row['Total_Ayats']),
                    "nom": row['Nom']
                }
            return SOMMAIRE_DB
        except Exception as e:
            print(f"Error loading sommaire: {e}")
    return SOMMAIRE_DB


def get_surah_for_page(page_num):
    """Retourne la liste des sourates présentes sur une page donnée."""
    if not SOMMAIRE_DB:
        return []
    
    surahs_on_page = []
    sorted_surahs = sorted(SOMMAIRE_DB.items(), key=lambda x: x[1]["page"])
    
    for i, (s_num, info) in enumerate(sorted_surahs):
        start_page = info["page"]
        # Trouver la page de fin (page de début de la sourate suivante - 1)
        if i + 1 < len(sorted_surahs):
            end_page = sorted_surahs[i + 1][1]["page"] - 1
        else:
            end_page = 604  # Dernière page du Coran
        
        if start_page <= page_num <= end_page:
            surahs_on_page.append(s_num)
    
    return surahs_on_page


def verify_surah_ayah(surah_num, ayah_num):
    """Vérifie si ayah_num est valide pour surah_num. 
    Retourne (surah_corrigé, ayah_corrigé) si dépassement."""
    if not SOMMAIRE_DB or surah_num not in SOMMAIRE_DB:
        return surah_num, ayah_num
    
    total = SOMMAIRE_DB[surah_num]["total_ayats"]
    
    if ayah_num <= total:
        return surah_num, ayah_num
    
    # Dépassement: on passe à la sourate suivante
    overflow = ayah_num - total
    next_surah = surah_num + 1
    
    if next_surah <= 114:
        return next_surah, overflow  # Le overflow devient le numéro d'ayah
    
    return surah_num, total  # Limite atteinte


def estimate_metadata_for_page(page_num):
    """Estime les métadonnées (juz, hizb, division, surah, ayah) pour une page donnée.
    
    Basé sur:
    - 604 pages total
    - 30 juz (environ 20 pages/juz)
    - 60 hizb (environ 10 pages/hizb)
    - 8 divisions par hizb (environ 1.25 pages/division)
    """
    # Pages spéciales
    if page_num <= 1:
        return {
            "juz": 1, "hizb": 1,
            "surah": 1, "ayah": 1
        }
    
    # Calculer juz (1-30) - environ 20 pages par juz
    # Page 2-21 = Juz 1, Page 22-41 = Juz 2, etc.
    juz = min(30, max(1, ((page_num - 2) // 20) + 1))
    
    # Calculer hizb (1-60) - 2 hizb par juz, environ 10 pages par hizb
    hizb = min(60, max(1, ((page_num - 2) // 10) + 1))
    
    # Calculer division dans le hizb
    # 8 divisions par hizb, environ 1.25 pages par division
    page_in_hizb = (page_num - 2) % 10  # Position dans le hizb (0-9)
    div_order = ["start", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8"]
    div_idx = min(7, int(page_in_hizb * 8 / 10))
    division = div_order[div_idx]
    
    # Trouver la sourate et l'ayah estimé
    surah = 1
    ayah = 1
    
    if SOMMAIRE_DB:
        surahs = get_surah_for_page(page_num)
        if surahs:
            surah = min(surahs)
            surah_info = SOMMAIRE_DB.get(surah, {})
            start_page = surah_info.get("page", page_num)
            total_ayats = surah_info.get("total_ayats", 1)
            
            # Estimer l'ayah: environ 15 ayats par page
            pages_into_surah = page_num - start_page
            ayah = min(total_ayats, max(1, pages_into_surah * 15 + 1))
    
    return {
        "juz": juz,
        "hizb": hizb,
        "surah": surah,
        "ayah": ayah
    }


def normalize_metadata(data):
    """Normalise la structure metadata avec le bon ordre des clés et le nouveau format."""
    if "metadata" not in data:
        data["metadata"] = {}
    
    meta = data["metadata"]
    
    # Migration: convertir ancien format vers nouveau
    if "starts_at_sourat" in meta:
        sourat = meta.pop("starts_at_sourat", 1)
        ayah = meta.get("starts_at_ayah", "1")
        # Si starts_at_ayah est déjà au format "S:A", ne pas modifier
        if ":" not in str(ayah):
            meta["starts_at_ayah"] = f"{sourat}:{ayah}"
    
    # Créer metadata avec ordre correct des clés (division est maintenant au niveau ayat)
    ordered_meta = {
        "page": meta.get("page", 1),
        "starts_at_ayah": meta.get("starts_at_ayah", "1:1"),
        "juz": meta.get("juz", 1),
        "hizb": meta.get("hizb", 1)
    }
    
    data["metadata"] = ordered_meta
    return data


def parse_ayah_ref(ref_str):
    """Parse une référence 'S:A' et retourne (surah, ayah)."""
    if ":" in str(ref_str):
        parts = str(ref_str).split(":")
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return 1, 1
    try:
        return 1, int(ref_str)
    except ValueError:
        return 1, 1


def check_coherence(data, prev_data=None):
    """Vérifie la cohérence logique des données.
    
    Retourne une liste de messages d'erreur/avertissement.
    """
    errors = []
    warnings = []
    
    ayats = data.get("ayats", [])
    meta = data.get("metadata", {})
    page_num = meta.get("page", 1)
    
    # 1. Vérifier la cohérence de la séquence S:A
    prev_surah, prev_ayah = None, None
    for i, ayat in enumerate(ayats):
        ayah_val = str(ayat.get("ayah", "1")).lower()
        if ayah_val == "basmala":
            continue
        
        surah = ayat.get("sourat_num", 1)
        try:
            ayah = int(ayah_val)
        except ValueError:
            errors.append(f"Ayat {i+1}: numéro d'ayah invalide '{ayah_val}'")
            continue
        
        # Vérifier séquence
        if prev_surah is not None:
            if surah == prev_surah:
                # Même sourate: ayah devrait être prev_ayah + 1
                if ayah != prev_ayah + 1:
                    warnings.append(f"Ayat {i+1}: séquence non continue S{surah}:A{ayah} (attendu A{prev_ayah + 1})")
            elif surah == prev_surah + 1:
                # Nouvelle sourate: ayah devrait être 1
                if ayah != 1:
                    warnings.append(f"Ayat {i+1}: nouvelle sourate S{surah} devrait commencer à A1 (trouvé A{ayah})")
            elif surah > prev_surah + 1:
                errors.append(f"Ayat {i+1}: saut de sourate S{prev_surah} → S{surah}")
            elif surah < prev_surah:
                errors.append(f"Ayat {i+1}: sourate décroissante S{surah} < S{prev_surah}")
        
        # Vérifier avec sommaire.csv
        if SOMMAIRE_DB and surah in SOMMAIRE_DB:
            total = SOMMAIRE_DB[surah]["total_ayats"]
            if ayah > total:
                errors.append(f"Ayat {i+1}: A{ayah} dépasse le total de S{surah} ({total} ayats)")
        
        prev_surah, prev_ayah = surah, ayah
    
    # 2. Vérifier cohérence avec starts_at_ayah
    starts_at = meta.get("starts_at_ayah", "1:1")
    start_s, start_a = parse_ayah_ref(starts_at)
    
    # Vérifier que starts_at_ayah ne dépasse pas le total de la sourate
    if SOMMAIRE_DB and start_s in SOMMAIRE_DB:
        total = SOMMAIRE_DB[start_s]["total_ayats"]
        if start_a > total:
            errors.append(
                f"Métadonnée starts_at_ayah={starts_at}: "
                f"Ayah {start_a} dépasse le total de Sourate {start_s} ({total} ayats)"
            )
    
    first_numbered = None
    for ayat in ayats:
        if str(ayat.get("ayah", "")).lower() != "basmala":
            first_numbered = ayat
            break
    
    if first_numbered:
        actual_s = first_numbered.get("sourat_num", 1)
        try:
            actual_a = int(first_numbered.get("ayah", "1"))
        except ValueError:
            actual_a = 1
        
        if (actual_s, actual_a) != (start_s, start_a):
            warnings.append(f"Métadonnée starts_at_ayah={starts_at} ne correspond pas au premier ayat S{actual_s}:A{actual_a}")
    
    # 3. Vérifier cohérence avec page précédente
    if prev_data:
        prev_ayats = prev_data.get("ayats", [])
        if prev_ayats:
            # Trouver le dernier ayat numéroté de la page précédente
            last_prev = None
            for ayat in reversed(prev_ayats):
                if str(ayat.get("ayah", "")).lower() != "basmala":
                    last_prev = ayat
                    break
            
            if last_prev and first_numbered:
                last_s = last_prev.get("sourat_num", 1)
                try:
                    last_a = int(last_prev.get("ayah", "1"))
                except ValueError:
                    last_a = 1
                
                # Le premier ayat de cette page devrait être last+1 ou nouvelle sourate
                expected_s, expected_a = verify_surah_ayah(last_s, last_a + 1)
                
                if (actual_s, actual_a) != (expected_s, expected_a):
                    # Vérifier si c'est une nouvelle sourate (avec basmala)
                    has_basmala = any(str(ay.get("ayah", "")).lower() == "basmala" for ay in ayats)
                    if not (has_basmala and actual_s == last_s + 1 and actual_a == 1):
                        warnings.append(
                            f"Discontinuité avec page précédente: "
                            f"dernier=S{last_s}:A{last_a} → premier=S{actual_s}:A{actual_a} "
                            f"(attendu S{expected_s}:A{expected_a})"
                        )
    
    # 4. Vérifier cohérence des divisions (séquence: start -> 1/8 -> 1/4 -> ... -> 7/8 -> start nouveau hizb)
    div_order = ["start", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8"]
    division = meta.get("division", "start")
    curr_hizb = meta.get("hizb", 1)
    curr_juz = meta.get("juz", 1)
    
    # Vérifier que la division est valide
    if division not in div_order:
        errors.append(f"Division invalide: '{division}' (valides: {div_order})")
    
    # Vérifier cohérence juz/hizb (juz = (hizb - 1) // 2 + 1)
    expected_juz = (curr_hizb - 1) // 2 + 1
    if curr_juz != expected_juz:
        warnings.append(f"Juz={curr_juz} incohérent avec hizb={curr_hizb} (attendu juz={expected_juz})")
    
    if prev_data:
        prev_meta = prev_data.get("metadata", {})
        prev_div = prev_meta.get("division", "start")
        prev_hizb = prev_meta.get("hizb", 1)
        prev_page = prev_meta.get("page", 0)
        
        # Vérifier seulement si pages consécutives
        if page_num == prev_page + 1 and prev_div in div_order and division in div_order:
            prev_idx = div_order.index(prev_div)
            curr_idx = div_order.index(division)
            
            # Cas 1: Même hizb
            if curr_hizb == prev_hizb:
                if curr_idx < prev_idx:
                    # Régression de division dans le même hizb
                    errors.append(
                        f"Division régresse: {prev_div} → {division} dans le même hizb {curr_hizb}"
                    )
                elif curr_idx == 0 and prev_idx > 0:
                    # start après une fraction = devrait être nouveau hizb
                    errors.append(
                        f"Division 'start' après '{prev_div}' dans le même hizb {curr_hizb} "
                        f"(devrait être hizb {prev_hizb + 1})"
                    )
            
            # Cas 2: Nouveau hizb (hizb + 1)
            elif curr_hizb == prev_hizb + 1:
                if curr_idx != 0:
                    warnings.append(
                        f"Nouveau hizb {curr_hizb} mais division='{division}' (attendu 'start')"
                    )
            
            # Cas 3: Saut de hizb
            elif curr_hizb > prev_hizb + 1:
                warnings.append(f"Saut de hizb: {prev_hizb} → {curr_hizb}")
            
            # Cas 4: Hizb décroissant
            elif curr_hizb < prev_hizb:
                errors.append(f"Hizb décroissant: {prev_hizb} → {curr_hizb}")
    
    # 5. Vérifier cohérence des divisions dans les ayats
    for i, ayat in enumerate(ayats):
        if "division" in ayat:
            div = ayat["division"]
            valid_divisions = ["start", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8"]
            if div not in valid_divisions:
                errors.append(f"Ayat {i}: division '{div}' invalide")
    
    return errors, warnings


def migrate_json_file(filepath):
    """Migre un fichier JSON vers le nouveau format."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Normaliser
        data = normalize_metadata(data)
        data = sort_json_structure_strictly(data)
        
        # Sauvegarder
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"Erreur migration {filepath}: {e}")
        return False


def migrate_all_json_files():
    """Migre tous les fichiers JSON vers le nouveau format."""
    if not os.path.exists(Config.JSON_DIR):
        return 0
    
    count = 0
    for filename in os.listdir(Config.JSON_DIR):
        if filename.endswith('.json'):
            filepath = os.path.join(Config.JSON_DIR, filename)
            if migrate_json_file(filepath):
                count += 1
    
    return count


def sort_json_structure_strictly(data):
    """Tri strict basé sur line_idx et position X décroissant (RTL pour arabe)."""
    if not data or "ayats" not in data or not data["ayats"]:
        return data
    
    # 1. Trier les polygones internes par ligne puis X décroissant (droite vers gauche)
    for ayat in data["ayats"]:
        if "rects" in ayat and ayat["rects"]:
            ayat["rects"].sort(key=lambda r: (int(r["line_idx"]), -int(r["coords"][0])))
    
    # 2. Trier les Ayats par ordre physique (ligne, puis X décroissant)
    def get_ayat_physical_key(ayat):
        if not ayat.get("rects"):
            return (999, 0)
        first_rect = ayat["rects"][0]
        return (int(first_rect["line_idx"]), -int(first_rect["coords"][0]))
    
    data["ayats"].sort(key=get_ayat_physical_key)
    return data


def find_previous_page_counters(current_page_num):
    """Cherche les compteurs de la page précédente.
    
    Si la page précédente n'existe pas, utilise estimate_metadata_for_page
    pour estimer les valeurs depuis sommaire.csv.
    """
    prev_page = current_page_num - 1
    if prev_page < 1:
        return 1, 0, {"juz": 1, "hizb": 1}
    
    # Chercher le fichier JSON de la page précédente
    for filename in os.listdir(Config.JSON_DIR) if os.path.exists(Config.JSON_DIR) else []:
        if not filename.endswith('.json'):
            continue
        match = re.search(r'(\d+)', filename)
        if match and int(match.group(1)) == prev_page:
            path = os.path.join(Config.JSON_DIR, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    prev_data = json.load(f)
                
                meta_extracted = prev_data.get("metadata", {})
                
                if "ayats" in prev_data and prev_data["ayats"]:
                    # Trouver le dernier ayah numéroté (ignorer basmala)
                    s_num = 1
                    a_num = 0
                    last_division = "start"
                    
                    # Récupérer la division du DERNIER ayat
                    if prev_data["ayats"]:
                        last_division = prev_data["ayats"][-1].get("division", "start")
                    
                    for ayat in reversed(prev_data["ayats"]):
                        s_num = int(ayat.get("sourat_num", 1))
                        ayah_val = str(ayat.get("ayah", "1")).lower()
                        if ayah_val != "basmala":
                            try:
                                a_num = int(ayah_val)
                                break
                            except ValueError:
                                continue
                    
                    # Vérifier avec sommaire si ayah dépasse le total
                    s_num, a_num = verify_surah_ayah(s_num, a_num)
                    
                    # Ajouter la division au metadata retourné
                    meta_extracted["last_division"] = last_division
                    
                    return s_num, a_num, meta_extracted
            except Exception:
                pass
    
    # Page précédente non trouvée: estimer depuis sommaire.csv
    estimated = estimate_metadata_for_page(current_page_num)
    estimated_meta = {
        "juz": estimated["juz"],
        "hizb": estimated["hizb"]
    }
    
    # Estimer le dernier ayah de la page précédente (ayah - 1 car on est au début de current_page)
    s_num = estimated["surah"]
    a_num = max(0, estimated["ayah"] - 1)
    
    return s_num, a_num, estimated_meta


# =============================================================================
# DETECTION ENGINE - Copie exacte de version_ameliorer.py
# =============================================================================

def robust_fine_tune(img_gray, x, y, w, h, min_w_ratio=0.12):
    """Affinage robuste des coordonnées du polygone."""
    if w < 15 or h < 15:
        return None
    roi = img_gray[max(0, y):min(img_gray.shape[0], y + h), 
                   max(0, x):min(img_gray.shape[1], x + w)]
    _, binary = cv2.threshold(roi, 200, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((2, 2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    coords = cv2.findNonZero(binary)
    if coords is None:
        return None
    rx, ry, rw, rh = cv2.boundingRect(coords)
    if rw < (w * min_w_ratio) or rw < 25:
        return None
    return [int(x + rx), int(y + ry), int(rw), int(rh)]


def process_page_v8_5(img, p_left, p_right, s_y, lh, ih, threshold_m, base_sourat, base_ayah):
    """
    Moteur de détection v8.5 - identique à l'app web.
    Retourne une liste de résultats bruts.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    t_left, t_right = int(p_left), int(w - p_right)
    
    m_tpl = cv2.imread(Config.MARKER_PATH)
    h_tpl = cv2.imread(Config.HEADER_PATH)
    
    # Détection des en-têtes de sourate
    headers = []
    if h_tpl is not None:
        res_h = cv2.matchTemplate(img, h_tpl, cv2.TM_CCOEFF_NORMED)
        loc_h = np.where(res_h >= 0.45)
        for pt in zip(*loc_h[::-1]):
            if not any(abs(pt[1] - head['y']) < 50 for head in headers):
                headers.append({'y': pt[1], 'h': h_tpl.shape[0]})
    headers = sorted(headers, key=lambda x: x['y'])
    
    # Détection des marqueurs d'ayat
    markers = []
    if m_tpl is not None:
        res_m = cv2.matchTemplate(img, m_tpl, cv2.TM_CCOEFF_NORMED)
        loc_m = np.where(res_m >= threshold_m)
        for pt in zip(*loc_m[::-1]):
            cx, cy = pt[0] + m_tpl.shape[1] // 2, pt[1] + m_tpl.shape[0] // 2
            if (t_left - 80) < cx < (t_right + 80):
                if not any(abs(cx - m['cx']) < 25 and abs(cy - m['cy']) < 25 for m in markers):
                    markers.append({'cx': cx, 'cy': cy, 'l': pt[0]})
    
    data_output = []
    current_segments = []
    curr_y = int(s_y)
    active_s, active_a = base_sourat, base_ayah
    
    while curr_y + lh <= h:
        # Vérifier si on est sur un en-tête
        is_h = [head for head in headers if abs(head['y'] - curr_y) < (lh / 2 + 20)]
        if is_h:
            if current_segments:
                active_a += 1
                data_output.append({
                    "nom_surah": SURAH_DB.get(active_s),
                    "number_ayat": active_a,
                    "segments": current_segments
                })
                current_segments = []
            active_s += 1
            active_a = 0
            curr_y = is_h[0]['y'] + is_h[0]['h'] + 15
            continue
        
        # Marqueurs sur cette ligne
        line_m = sorted(
            [m for m in markers if curr_y - 45 <= m['cy'] <= curr_y + lh + 45],
            key=lambda x: x['cx'],
            reverse=True
        )
        
        y_ref = int(np.mean([m['cy'] for m in line_m])) - (lh // 2) if line_m else curr_y
        if line_m:
            curr_y = y_ref
        
        x_cursor = t_right
        
        if not line_m:
            seg = robust_fine_tune(gray, t_left, y_ref, x_cursor - t_left, lh)
            if seg:
                current_segments.append(seg)
        else:
            for m in line_m:
                seg = robust_fine_tune(gray, m['l'], y_ref, x_cursor - m['l'], lh)
                if seg:
                    current_segments.append(seg)
                    active_a += 1
                    data_output.append({
                        "nom_surah": SURAH_DB.get(active_s),
                        "number_ayat": active_a,
                        "segments": current_segments
                    })
                    current_segments = []
                x_cursor = m['l']
            
            seg = robust_fine_tune(gray, t_left, y_ref, x_cursor - t_left, lh)
            if seg:
                current_segments.append(seg)
        
        curr_y += lh + ih
    
    return data_output


def transform_output_to_v18_structure(v8_results, p_num, base_sourat, base_ayah, inherited_meta):
    """Transforme la sortie v8 en structure v18 - nouveau format avec starts_at_ayah = 'S:A'."""
    first_ayah = base_ayah + 1
    # Récupérer la division du dernier ayat de la page précédente
    inherited_division = inherited_meta.get("last_division", "start")
    
    new_data = {
        "metadata": {
            "page": p_num,
            "starts_at_ayah": f"{base_sourat}:{first_ayah}",
            "juz": inherited_meta.get("juz", 1),
            "hizb": inherited_meta.get("hizb", 1)
        },
        "ayats": []
    }
    
    if not v8_results:
        return new_data
    
    active_s, active_a = base_sourat, base_ayah
    flat_blocks = []
    
    for res in v8_results:
        s_name = res.get("nom_surah")
        s_num = next((num for num, name in SURAH_DB.items() if name == s_name), active_s)
        if s_num != active_s:
            active_s = s_num
            active_a = 0
        active_a += 1
        
        for idx, rect in enumerate(res.get("segments", [])):
            flat_blocks.append({
                "sourat_num": active_s,
                "ayah": str(active_a),
                "type": "Début" if idx == 0 else "Suite",
                "coords": rect,
                "y_center": rect[1] + (rect[3] / 2)
            })
    
    if not flat_blocks:
        return new_data
    
    # Assigner les indices de ligne
    flat_blocks.sort(key=lambda x: x["y_center"])
    current_line_idx = 1
    last_y_center = flat_blocks[0]["y_center"]
    
    for item in flat_blocks:
        if item["y_center"] - last_y_center > 65:
            current_line_idx += 1
        item["line_idx"] = current_line_idx
        last_y_center = item["y_center"]
    
    # Construire la structure finale
    for item in flat_blocks:
        matched_ayat = next(
            (ay for ay in new_data["ayats"] 
             if ay["sourat_num"] == item["sourat_num"] and ay["ayah"] == item["ayah"]),
            None
        )
        rect_obj = {
            "line_idx": item["line_idx"],
            "type": item["type"],
            "coords": item["coords"]
        }
        if matched_ayat:
            matched_ayat["rects"].append(rect_obj)
        else:
            new_data["ayats"].append({
                "sourat_num": item["sourat_num"],
                "ayah": item["ayah"],
                "division": inherited_division,
                "rects": [rect_obj]
            })
    
    return sort_json_structure_strictly(new_data)


# =============================================================================
# CANVAS WIDGET
# =============================================================================
class CanvasWidget(QLabel):
    """Image display with polygon overlay."""
    
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.cv_image = None
        self.scale = 1.0
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #1a1a1a;")
        self.setMouseTracking(True)
    
    def set_image(self, cv_image):
        """Set the image to display."""
        self.cv_image = cv_image
        self.refresh()
    
    def refresh(self):
        """Redraw the canvas with current data."""
        if self.cv_image is None:
            self.clear()
            return
        
        # Create display image
        display = self.cv_image.copy()
        
        # Draw polygons
        data = self.editor.data
        focus_a = self.editor.focus_ayat
        focus_r = self.editor.focus_rect
        selected = self.editor.selected_polygons
        
        # Palette de couleurs distinctes (BGR) - alternent bien visuellement
        DISTINCT_COLORS = [
            (255, 100, 100),   # Rouge clair
            (100, 255, 100),   # Vert clair
            (100, 100, 255),   # Bleu clair
            (255, 255, 100),   # Jaune
            (255, 100, 255),   # Magenta
            (100, 255, 255),   # Cyan
            (255, 180, 100),   # Orange
            (180, 100, 255),   # Violet
        ]
        
        for a_idx, ayat in enumerate(data.get("ayats", [])):
            # Couleur distincte basée sur l'index (alterne entre couleurs très différentes)
            color = DISTINCT_COLORS[a_idx % len(DISTINCT_COLORS)]
            
            for r_idx, rect in enumerate(ayat.get("rects", [])):
                coords = rect.get("coords", [0, 0, 100, 50])
                x, y, w, h = coords
                
                is_focus = (a_idx == focus_a and r_idx == focus_r)
                is_selected = (a_idx, r_idx) in selected
                
                # Fill with transparency
                overlay = display.copy()
                cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1)
                alpha = 0.35 if is_focus else 0.2
                cv2.addWeighted(overlay, alpha, display, 1 - alpha, 0, display)
                
                # Border
                if is_focus:
                    border_color = (0, 255, 200)  # Cyan
                    thickness = 3
                elif is_selected:
                    border_color = (255, 165, 0)  # Orange
                    thickness = 2
                else:
                    border_color = color
                    thickness = 1
                
                cv2.rectangle(display, (x, y), (x + w, y + h), border_color, thickness)
                
                # Label
                label = f"S{ayat.get('sourat_num', '?')} A{ayat.get('ayah', '?')}"
                if is_focus:
                    cv2.putText(display, label, (x + 4, y - 6),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, border_color, 2)
        
        # Convert to QPixmap
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        
        # Scale to fit
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.scale = scaled.width() / pixmap.width() if pixmap.width() > 0 else 1
        self.setPixmap(scaled)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle polygon selection."""
        if self.cv_image is None:
            return
        
        # Calculate real coordinates
        pixmap = self.pixmap()
        if not pixmap:
            return
        
        # Get click position relative to image
        rect = self.rect()
        pix_rect = pixmap.rect()
        pix_rect.moveCenter(rect.center())
        
        click_x = (event.position().x() - pix_rect.x()) / self.scale
        click_y = (event.position().y() - pix_rect.y()) / self.scale
        
        # Check modifier for multi-select
        multi = event.modifiers() & (Qt.KeyboardModifier.ControlModifier | 
                                      Qt.KeyboardModifier.MetaModifier)
        
        # Find clicked polygon
        for a_idx, ayat in enumerate(self.editor.data.get("ayats", [])):
            for r_idx, rect in enumerate(ayat.get("rects", [])):
                c = rect.get("coords", [0, 0, 0, 0])
                if c[0] <= click_x <= c[0] + c[2] and c[1] <= click_y <= c[1] + c[3]:
                    if multi:
                        poly = (a_idx, r_idx)
                        if poly in self.editor.selected_polygons:
                            self.editor.selected_polygons.remove(poly)
                        else:
                            self.editor.selected_polygons.append(poly)
                    else:
                        self.editor.selected_polygons = []
                    
                    self.editor.focus_ayat = a_idx
                    self.editor.focus_rect = r_idx
                    self.editor.on_selection_changed()
                    return
        
        # Click on empty - deselect
        if not multi:
            self.editor.selected_polygons = []
            self.editor.on_selection_changed()


# =============================================================================
# MAIN EDITOR WINDOW
# =============================================================================
class QuranEditor(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quran Ayat Editor")
        self.setMinimumSize(1400, 900)
        
        # State
        self.data = {"ayats": [], "metadata": {}}
        self.focus_ayat = 0
        self.focus_rect = 0
        self.selected_polygons = []
        self.history = []
        self.redo_stack = []
        self.current_image = None
        self.current_image_path = ""
        self.current_json_path = ""
        self.image_files = []
        self.has_unsaved_changes = False
        
        # Load resources
        self.surah_db = load_surah_database()
        load_sommaire_database()  # Pour vérification des sourates
        self.image_files = self._load_image_list()
        
        # Build UI
        self._setup_ui()
        self._setup_shortcuts()
        
        # Suggestion de page au démarrage
        if self.image_files:
            self._show_startup_suggestion()
    
    def _load_image_list(self):
        """Get list of images in directory."""
        if not os.path.exists(Config.IMAGE_DIR):
            return []
        
        files = [f for f in os.listdir(Config.IMAGE_DIR)
                if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        return sorted(files)
    
    def _find_first_gap(self):
        """
        Trouve la première page manquante dans la séquence des JSON.
        Retourne (page_manquante, dernière_page_faite) ou (None, None) si tout est fait.
        """
        if not os.path.exists(Config.JSON_DIR):
            return 1, 0  # Commencer à la page 1
        
        # Récupérer tous les numéros de pages des JSON existants
        existing_pages = set()
        for fn in os.listdir(Config.JSON_DIR):
            if fn.endswith('.json'):
                match = re.search(r'(\d+)', fn)
                if match:
                    existing_pages.add(int(match.group(1)))
        
        if not existing_pages:
            return 1, 0  # Aucun JSON, commencer à 1
        
        # Trouver les pages disponibles (images)
        available_pages = set()
        for fn in self.image_files:
            match = re.search(r'(\d+)', fn)
            if match:
                available_pages.add(int(match.group(1)))
        
        if not available_pages:
            return None, None
        
        # Chercher la première coupure dans la séquence
        # Commencer à la plus petite page disponible
        min_page = min(available_pages)
        max_page = max(available_pages)
        
        last_done = 0
        for page_num in range(min_page, max_page + 1):
            if page_num not in available_pages:
                continue  # Page image n'existe pas, ignorer
            
            if page_num in existing_pages:
                last_done = page_num
            else:
                # Première page manquante trouvée
                return page_num, last_done
        
        # Tout est fait
        return None, last_done
    
    def _show_startup_suggestion(self):
        """Affiche une suggestion de page au démarrage."""
        first_gap, last_done = self._find_first_gap()
        
        if first_gap is None:
            # Tout est fait, proposer de réviser
            if last_done > 0:
                msg = f"✅ Toutes les pages jusqu'à {last_done} sont annotées!\n\nVoulez-vous réviser depuis le début?"
                reply = QMessageBox.question(
                    self, "Annotation complète",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.load_page(0)
                else:
                    self.load_page(len(self.image_files) - 1)
            else:
                self.load_page(0)
            return
        
        # Proposer de continuer à la première page manquante
        msg = f"📖 Dernière page annotée: {last_done}\n\n"
        msg += f"Voulez-vous continuer à la page {first_gap}?"
        
        reply = QMessageBox.question(
            self, "Continuer l'annotation",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Trouver l'index de la page suggérée
            target_filename = f"page_{first_gap:03d}"
            for idx, fn in enumerate(self.image_files):
                if target_filename in fn:
                    self.load_page(idx)
                    return
            # Fallback si format différent
            for idx, fn in enumerate(self.image_files):
                match = re.search(r'(\d+)', fn)
                if match and int(match.group(1)) == first_gap:
                    self.load_page(idx)
                    return
        
        # Non ou page non trouvée: charger la première page
        self.load_page(0)
    
    def _setup_ui(self):
        """Build the user interface."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # === LEFT PANEL: Navigation ===
        left = QWidget()
        left.setFixedWidth(350)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(12)
        
        # Page navigation
        nav_group = QGroupBox("Navigation")
        nav_layout = QVBoxLayout(nav_group)
        
        # Page selector (Enter pour naviguer)
        page_row = QHBoxLayout()
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 999)
        self.page_spin.setPrefix("Page ")
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.editingFinished.connect(self._go_to_page)
        page_row.addWidget(self.page_spin, 1)
        
        go_btn = QPushButton("Aller")
        go_btn.clicked.connect(self._go_to_page)
        page_row.addWidget(go_btn)
        nav_layout.addLayout(page_row)
        
        # File dropdown
        self.file_combo = QComboBox()
        self.file_combo.addItems(self.image_files)
        self.file_combo.currentIndexChanged.connect(self._on_file_combo_changed)
        nav_layout.addWidget(self.file_combo)
        
        # Prev/Next
        nav_btns = QHBoxLayout()
        prev_btn = QPushButton("◀ Précédent")
        prev_btn.clicked.connect(lambda: self._nav_page(-1))
        next_btn = QPushButton("Suivant ▶")
        next_btn.clicked.connect(lambda: self._nav_page(1))
        nav_btns.addWidget(prev_btn)
        nav_btns.addWidget(next_btn)
        nav_layout.addLayout(nav_btns)
        
        left_layout.addWidget(nav_group)
        
        # Ayat list (arbre avec sous-items polygones)
        self.ayat_group = QGroupBox("Ayats détectées (0)")
        ayat_layout = QVBoxLayout(self.ayat_group)
        
        self.ayat_tree = QTreeWidget()
        self.ayat_tree.setHeaderLabels(["Ayat / Polygone"])
        self.ayat_tree.header().setVisible(False)
        self.ayat_tree.setIndentation(16)
        self.ayat_tree.itemClicked.connect(self._on_tree_item_clicked)
        self.ayat_tree.itemExpanded.connect(self._on_tree_item_expanded)
        ayat_layout.addWidget(self.ayat_tree)
        
        # Add/Delete buttons - Row 1
        btn_row = QHBoxLayout()
        add_ayat_btn = QPushButton("+ Ayat")
        add_ayat_btn.clicked.connect(self.add_ayat)
        add_poly_btn = QPushButton("+ Poly")
        add_poly_btn.clicked.connect(self.add_polygon)
        basmala_btn = QPushButton("☪ Basmala")
        basmala_btn.setToolTip("Extraire le polygone sélectionné comme Basmala")
        basmala_btn.clicked.connect(self.extract_basmala)
        del_btn = QPushButton("🗑")
        del_btn.setFixedWidth(36)
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self.delete_polygon)
        btn_row.addWidget(add_ayat_btn)
        btn_row.addWidget(add_poly_btn)
        btn_row.addWidget(basmala_btn)
        btn_row.addWidget(del_btn)
        ayat_layout.addLayout(btn_row)
        
        # Correction button - Row 2
        btn_row2 = QHBoxLayout()
        correct_btn = QPushButton("🔢 Corriger Séquence")
        correct_btn.setToolTip("Corrige automatiquement la numérotation S/A depuis le premier ayat")
        correct_btn.clicked.connect(self._manual_correct_sequence)
        btn_row2.addWidget(correct_btn)
        ayat_layout.addLayout(btn_row2)
        
        # Merge buttons - Row 3 (correction d'erreurs de détection)
        btn_row3 = QHBoxLayout()
        merge_poly_btn = QPushButton("⬆ Fusionner Poly")
        merge_poly_btn.setToolTip("Déplace le polygone sélectionné vers l'ayat précédent (Ctrl+M)")
        merge_poly_btn.clicked.connect(self.merge_polygon_to_previous)
        merge_ayat_btn = QPushButton("⬆⬆ Fusionner Ayat")
        merge_ayat_btn.setToolTip("Fusionne tous les polygones de cet ayat avec l'ayat précédent (Ctrl+Shift+M)")
        merge_ayat_btn.clicked.connect(self.merge_ayat_to_previous)
        btn_row3.addWidget(merge_poly_btn)
        btn_row3.addWidget(merge_ayat_btn)
        ayat_layout.addLayout(btn_row3)
        
        left_layout.addWidget(self.ayat_group, 1)
        
        # Quick actions
        action_row = QHBoxLayout()
        save_btn = QPushButton("💾 Sauver")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.save_json)
        upload_btn = QPushButton("📤 Upload HF")
        upload_btn.setToolTip("Uploader les annotations vers Hugging Face")
        upload_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        upload_btn.clicked.connect(self._upload_annotations_to_hf)
        undo_btn = QPushButton("↩")
        undo_btn.setFixedWidth(36)
        undo_btn.clicked.connect(self.undo)
        redo_btn = QPushButton("↪")
        redo_btn.setFixedWidth(36)
        redo_btn.clicked.connect(self.redo)
        action_row.addWidget(save_btn, 1)
        action_row.addWidget(upload_btn)
        action_row.addWidget(undo_btn)
        action_row.addWidget(redo_btn)
        left_layout.addLayout(action_row)
        
        splitter.addWidget(left)
        
        # === CENTER: Canvas ===
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.canvas = CanvasWidget(self)
        scroll.setWidget(self.canvas)
        center_layout.addWidget(scroll)
        
        # Info bar
        self.info_label = QLabel("⌘+Clic: Multi | ⇧+Flèches: Déplacer | T: Thumn | ⇧+T: Annuler Thumn | ⌘+M: Fusionner")
        self.info_label.setObjectName("info")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.info_label)
        
        splitter.addWidget(center)
        
        # === RIGHT PANEL: Properties ===
        right = QWidget()
        right.setFixedWidth(320)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(12)
        
        # Polygon properties
        props_group = QGroupBox("Propriétés du polygone")
        props_layout = QVBoxLayout(props_group)
        
        # Sourate
        s_row = QHBoxLayout()
        s_row.addWidget(QLabel("Sourate:"))
        self.sourat_spin = QSpinBox()
        self.sourat_spin.setRange(1, 114)
        self.sourat_spin.valueChanged.connect(self._on_sourat_changed)
        s_row.addWidget(self.sourat_spin, 1)
        props_layout.addLayout(s_row)
        
        # Ayah avec checkbox Basmala
        a_row = QHBoxLayout()
        a_row.addWidget(QLabel("Ayah:"))
        self.ayah_spin = QSpinBox()
        self.ayah_spin.setRange(0, 300)
        self.ayah_spin.valueChanged.connect(self._on_ayah_changed)
        a_row.addWidget(self.ayah_spin)
        self.basmala_check = QCheckBox("Basmala")
        self.basmala_check.toggled.connect(self._on_basmala_toggled)
        a_row.addWidget(self.basmala_check)
        self.sajda_check = QCheckBox("Sajda")
        self.sajda_check.toggled.connect(self._on_sajda_toggled)
        a_row.addWidget(self.sajda_check)
        props_layout.addLayout(a_row)
        
        # Division row
        div_row = QHBoxLayout()
        div_row.addWidget(QLabel("Division:"))
        self.division_combo = QComboBox()
        self.division_combo.addItems(["start", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8"])
        self.division_combo.currentTextChanged.connect(self._on_division_changed)
        div_row.addWidget(self.division_combo)
        props_layout.addLayout(div_row)
        
        # Coordinates
        coords_label = QLabel("Coordonnées")
        coords_label.setObjectName("sectionTitle")
        props_layout.addWidget(coords_label)
        
        coord_grid = QHBoxLayout()
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 5000)
        self.x_spin.setPrefix("X: ")
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 5000)
        self.y_spin.setPrefix("Y: ")
        coord_grid.addWidget(self.x_spin)
        coord_grid.addWidget(self.y_spin)
        props_layout.addLayout(coord_grid)
        
        size_grid = QHBoxLayout()
        self.w_spin = QSpinBox()
        self.w_spin.setRange(10, 5000)
        self.w_spin.setPrefix("W: ")
        self.h_spin = QSpinBox()
        self.h_spin.setRange(10, 500)
        self.h_spin.setPrefix("H: ")
        size_grid.addWidget(self.w_spin)
        size_grid.addWidget(self.h_spin)
        props_layout.addLayout(size_grid)
        
        # Line index
        line_row = QHBoxLayout()
        line_row.addWidget(QLabel("Ligne:"))
        self.line_idx_spin = QSpinBox()
        self.line_idx_spin.setRange(1, 20)
        self.line_idx_spin.valueChanged.connect(self._on_line_idx_changed)
        line_row.addWidget(self.line_idx_spin)
        props_layout.addLayout(line_row)
        
        for spin in [self.x_spin, self.y_spin, self.w_spin, self.h_spin]:
            spin.valueChanged.connect(self._on_coords_changed)
        
        # Quick adjustments
        adj_label = QLabel("Ajustements rapides")
        adj_label.setObjectName("sectionTitle")
        props_layout.addWidget(adj_label)
        
        # Step parameters
        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("Pas X:"))
        self.step_x_spin = QSpinBox()
        self.step_x_spin.setRange(1, 100)
        self.step_x_spin.setValue(5)
        step_row.addWidget(self.step_x_spin)
        step_row.addWidget(QLabel("Pas W:"))
        self.step_w_spin = QSpinBox()
        self.step_w_spin.setRange(1, 100)
        self.step_w_spin.setValue(5)
        step_row.addWidget(self.step_w_spin)
        props_layout.addLayout(step_row)
        
        # Presets
        preset_row = QHBoxLayout()
        for name in ["M1", "M2", "T3"]:
            btn = QPushButton(name)
            btn.clicked.connect(lambda _, n=name: self.apply_preset(n))
            preset_row.addWidget(btn)
        props_layout.addLayout(preset_row)
        
        # Y/H adjustment
        yh_row = QHBoxLayout()
        for label, key in [("Y ↑", "y-"), ("Y ↓", "y+"), 
                           ("H −", "h-"), ("H +", "h+")]:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, k=key: self._adjust_by_step(k))
            yh_row.addWidget(btn)
        props_layout.addLayout(yh_row)
        
        # X/W adjustment
        xw_row = QHBoxLayout()
        for label, key in [("X ◀", "x-"), ("X ▶", "x+"),
                           ("W −", "w-"), ("W +", "w+")]:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, k=key: self._adjust_by_step(k))
            xw_row.addWidget(btn)
        props_layout.addLayout(xw_row)
        
        right_layout.addWidget(props_group)
        
        # Detection
        detect_group = QGroupBox("Détection automatique")
        detect_layout = QVBoxLayout(detect_group)
        
        # Parameters in compact grid
        param_row1 = QHBoxLayout()
        param_row1.addWidget(QLabel("Marge G:"))
        self.pad_left_spin = QSpinBox()
        self.pad_left_spin.setRange(0, 500)
        self.pad_left_spin.setValue(Config.PADDING_LEFT_ODD)  # Défaut: page impaire
        param_row1.addWidget(self.pad_left_spin)
        param_row1.addWidget(QLabel("D:"))
        self.pad_right_spin = QSpinBox()
        self.pad_right_spin.setRange(0, 500)
        self.pad_right_spin.setValue(Config.PADDING_RIGHT_ODD)  # Défaut: page impaire
        param_row1.addWidget(self.pad_right_spin)
        detect_layout.addLayout(param_row1)
        
        param_row2 = QHBoxLayout()
        param_row2.addWidget(QLabel("Départ Y:"))
        self.start_y_spin = QSpinBox()
        self.start_y_spin.setRange(0, 1000)
        self.start_y_spin.setValue(Config.START_Y)
        param_row2.addWidget(self.start_y_spin)
        param_row2.addWidget(QLabel("H:"))
        self.line_h_spin = QSpinBox()
        self.line_h_spin.setRange(20, 200)
        self.line_h_spin.setValue(Config.LINE_HEIGHT)
        param_row2.addWidget(self.line_h_spin)
        detect_layout.addLayout(param_row2)
        
        param_row3 = QHBoxLayout()
        param_row3.addWidget(QLabel("Sourate:"))
        self.base_sourat_spin = QSpinBox()
        self.base_sourat_spin.setRange(1, 114)
        param_row3.addWidget(self.base_sourat_spin)
        param_row3.addWidget(QLabel("Ayah:"))
        self.base_ayah_spin = QSpinBox()
        self.base_ayah_spin.setRange(0, 300)
        param_row3.addWidget(self.base_ayah_spin)
        detect_layout.addLayout(param_row3)
        
        detect_btn = QPushButton("🔍 Lancer la détection")
        detect_btn.setObjectName("primary")
        detect_btn.clicked.connect(self.run_detection)
        detect_layout.addWidget(detect_btn)
        
        # Alignment buttons
        align_row = QHBoxLayout()
        align_h_btn = QPushButton("↔ Aligner H")
        align_h_btn.clicked.connect(self.align_horizontal)
        align_v_btn = QPushButton("↕ Aligner V")
        align_v_btn.clicked.connect(self.align_vertical)
        align_all_btn = QPushButton("▣ Tout")
        align_all_btn.clicked.connect(self.align_all)
        align_row.addWidget(align_all_btn)
        align_row.addWidget(align_h_btn)
        align_row.addWidget(align_v_btn)
        detect_layout.addLayout(align_row)
        
        right_layout.addWidget(detect_group)
        
        # Metadata
        meta_group = QGroupBox("Métadonnées")
        meta_layout = QVBoxLayout(meta_group)
        
        meta_row1 = QHBoxLayout()
        meta_row1.addWidget(QLabel("Juz:"))
        self.juz_spin = QSpinBox()
        self.juz_spin.setRange(1, 30)
        self.juz_spin.valueChanged.connect(self._on_meta_changed)
        meta_row1.addWidget(self.juz_spin)
        meta_row1.addWidget(QLabel("Hizb:"))
        self.hizb_spin = QSpinBox()
        self.hizb_spin.setRange(1, 60)
        self.hizb_spin.valueChanged.connect(self._on_meta_changed)
        meta_row1.addWidget(self.hizb_spin)
        meta_layout.addLayout(meta_row1)
        
        # Division est maintenant stockée au niveau ayat, pas dans metadata
        # Afficher uniquement "Début"
        meta_row2 = QHBoxLayout()
        meta_row2.addWidget(QLabel("Début:"))
        self.starts_at_edit = QLineEdit()
        self.starts_at_edit.setPlaceholderText("1:1")
        self.starts_at_edit.editingFinished.connect(self._on_meta_changed)
        meta_row2.addWidget(self.starts_at_edit)
        meta_layout.addLayout(meta_row2)
        
        right_layout.addWidget(meta_group)
        right_layout.addStretch()
        
        splitter.addWidget(right)
        
        # Set splitter proportions
        splitter.setSizes([260, 860, 280])
        
        # Status bar
        self.statusBar().showMessage("Prêt")
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        shortcuts = [
            ("Ctrl+S", self.save_json),
            ("Ctrl+Z", self.undo),
            ("Ctrl+Shift+Z", self.redo),
            ("Ctrl+N", self.add_ayat),
            ("Ctrl+P", self.add_polygon),
            ("Delete", self.delete_polygon),
            # Shift+Arrow: pas de 5 pixels
            ("Shift+Up", lambda: self.adjust_coord("y", -5)),
            ("Shift+Down", lambda: self.adjust_coord("y", 5)),
            ("Shift+Left", lambda: self.adjust_coord("x", -5)),
            ("Shift+Right", lambda: self.adjust_coord("x", 5)),
            # Alt+Arrow: ajuster taille
            ("Alt+Up", lambda: self.adjust_coord("h", -5)),
            ("Alt+Down", lambda: self.adjust_coord("h", 5)),
            ("Alt+Left", lambda: self.adjust_coord("w", -20)),
            ("Alt+Right", lambda: self.adjust_coord("w", 20)),
            ("M", lambda: self.apply_preset("M1")),
            ("T", lambda: self.apply_preset("T3")),
            ("Shift+T", self.reset_thumn),  # Annuler marque thumn
            ("PgUp", lambda: self._nav_page(-1)),
            ("PgDown", lambda: self._nav_page(1)),
            # Merge shortcuts (correction d'erreurs de détection)
            ("Ctrl+M", self.merge_polygon_to_previous),
            ("Ctrl+Shift+M", self.merge_ayat_to_previous),
        ]
        
        for key, func in shortcuts:
            QShortcut(QKeySequence(key), self, func)
    
    # =========================================================================
    # PAGE LOADING
    # =========================================================================
    def load_page(self, index):
        """Load a page image and its JSON data."""
        if index < 0 or index >= len(self.image_files):
            return
        
        filename = self.image_files[index]
        
        # Extraire le numéro de page
        match = re.search(r'(\d+)', filename)
        page_num = int(match.group(1)) if match else 1
        
        self.current_image_path = os.path.join(Config.IMAGE_DIR, filename)
        
        # Determine JSON path
        base = os.path.splitext(filename)[0]
        self.current_json_path = os.path.join(Config.JSON_DIR, base + ".json")
        
        # Load image
        self.current_image = cv2.imread(self.current_image_path)
        if self.current_image is None:
            QMessageBox.warning(self, "Erreur", f"Impossible de charger: {filename}")
            return
        
        # Load or create JSON
        if os.path.exists(self.current_json_path):
            with open(self.current_json_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            # Mettre à jour les spinbox depuis les données existantes
            self._update_spinbox_from_data()
        else:
            # Auto-detect
            self._auto_detect_for_page(filename)
        
        # Reset state
        self.focus_ayat = 0
        self.focus_rect = 0
        self.selected_polygons = []
        self.history = []
        self.redo_stack = []
        self.has_unsaved_changes = False
        
        # Update UI
        self.file_combo.blockSignals(True)
        self.file_combo.setCurrentIndex(index)
        self.file_combo.blockSignals(False)
        
        # Extract page number
        match = re.search(r'(\d+)', filename)
        if match:
            self.page_spin.setValue(int(match.group(1)))
        
        self.canvas.set_image(self.current_image)
        self._update_ayat_list()
        self._update_properties()
        self.statusBar().showMessage(f"📄 {filename} chargé")
    
    def _update_spinbox_from_data(self):
        """Met à jour les spinbox de détection depuis les données JSON existantes."""
        # Trouver le premier ayat non-basmala pour avoir le numéro de sourate/ayah
        if self.data.get("ayats"):
            for ayat in self.data["ayats"]:
                ayah_val = str(ayat.get("ayah", "1")).lower()
                if ayah_val != "basmala":
                    self.base_sourat_spin.setValue(int(ayat.get("sourat_num", 1)))
                    try:
                        self.base_ayah_spin.setValue(int(ayah_val))
                    except ValueError:
                        self.base_ayah_spin.setValue(1)
                    break
        
        # Mettre à jour les marges selon la parité de la page
        page_num = self.data.get("metadata", {}).get("page", 1)
        if page_num % 2 == 0:
            self.pad_left_spin.setValue(Config.PADDING_LEFT_EVEN)
            self.pad_right_spin.setValue(Config.PADDING_RIGHT_EVEN)
        else:
            self.pad_left_spin.setValue(Config.PADDING_LEFT_ODD)
            self.pad_right_spin.setValue(Config.PADDING_RIGHT_ODD)
    
    def _auto_detect_for_page(self, filename):
        """Run auto-detection for a new page - utilise process_page_v8_5."""
        # Extraire le numéro de page
        match = re.search(r'(\d+)', filename)
        page_num = int(match.group(1)) if match else 1
        
        # Marges selon parité de la page
        if page_num % 2 == 0:  # Page paire
            pad_left = Config.PADDING_LEFT_EVEN
            pad_right = Config.PADDING_RIGHT_EVEN
        else:  # Page impaire
            pad_left = Config.PADDING_LEFT_ODD
            pad_right = Config.PADDING_RIGHT_ODD
        
        # Chercher les compteurs de la page précédente (identique à l'app web)
        base_sourat, base_ayah, inherited_meta = find_previous_page_counters(page_num)
        
        # Vérifier si la page précédente existe (sauf pour page 1 et 2)
        if page_num > 2:
            prev_page = page_num - 1
            prev_json_exists = False
            for fn in os.listdir(Config.JSON_DIR) if os.path.exists(Config.JSON_DIR) else []:
                if fn.endswith('.json'):
                    m = re.search(r'(\d+)', fn)
                    if m and int(m.group(1)) == prev_page:
                        prev_json_exists = True
                        break
            
            if not prev_json_exists:
                estimated = estimate_metadata_for_page(page_num)
                self.statusBar().showMessage(
                    f"⚠️ Page {prev_page} manquante - Estimations: S{estimated['surah']}:A{estimated['ayah']}, Juz {estimated['juz']}, Hizb {estimated['hizb']}"
                )
        
        # Si pas de données de page précédente, utiliser sommaire.csv
        if base_sourat == 1 and base_ayah == 0 and page_num > 2:
            surahs = get_surah_for_page(page_num)
            if surahs:
                # Prendre la première sourate de cette page
                base_sourat = min(surahs)
                # Estimer l'ayah de début basé sur la page de début de la sourate
                surah_info = SOMMAIRE_DB.get(base_sourat, {})
                start_page = surah_info.get("page", page_num)
                # Approximation: ~15 ayats par page
                estimated_ayah = max(0, (page_num - start_page) * 15)
                base_ayah = min(estimated_ayah, surah_info.get("total_ayats", 1) - 1)
        
        # Lancer la détection avec process_page_v8_5
        v8_result = process_page_v8_5(
            self.current_image,
            pad_left,
            pad_right,
            Config.START_Y,
            Config.LINE_HEIGHT,
            Config.INTER_HEIGHT,
            Config.THRESHOLD,
            base_sourat,
            base_ayah
        )
        
        # Transformer en structure v18
        self.data = transform_output_to_v18_structure(
            v8_result, page_num, base_sourat, base_ayah, inherited_meta
        )
        
        # Mettre à jour les spinbox de détection
        self.base_sourat_spin.setValue(base_sourat)
        self.base_ayah_spin.setValue(base_ayah)
        self.pad_left_spin.setValue(pad_left)
        self.pad_right_spin.setValue(pad_right)
    
    def _on_file_combo_changed(self, index):
        """Handle file combo change - check unsaved changes first."""
        if not self._check_unsaved_changes():
            # Restaurer l'index précédent
            self.file_combo.blockSignals(True)
            for i, fn in enumerate(self.image_files):
                if fn in self.current_image_path:
                    self.file_combo.setCurrentIndex(i)
                    break
            self.file_combo.blockSignals(False)
            return
        self.load_page(index)
    
    def _go_to_page(self):
        """Navigate to specific page number."""
        if not self._check_unsaved_changes():
            return
        
        target = self.page_spin.value()
        
        for idx, filename in enumerate(self.image_files):
            match = re.search(r'(\d+)', filename)
            if match and int(match.group(1)) == target:
                self.load_page(idx)
                return
        
        QMessageBox.warning(self, "Page introuvable", f"Pas d'image pour la page {target}")
    
    def _check_unsaved_changes(self):
        """Vérifie s'il y a des modifications non sauvegardées.
        
        Retourne True si on peut continuer (sauvegardé ou abandonné).
        Retourne False si l'utilisateur annule.
        """
        if not self.has_unsaved_changes or not self.data.get("ayats"):
            return True
        
        reply = QMessageBox.question(
            self,
            "Modifications non sauvegardées",
            "⚠️ La page actuelle a des modifications non sauvegardées.\n\n"
            "Voulez-vous sauvegarder avant de continuer?",
            QMessageBox.StandardButton.Save | 
            QMessageBox.StandardButton.Discard | 
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save
        )
        
        if reply == QMessageBox.StandardButton.Save:
            self.save_json()
            return True
        elif reply == QMessageBox.StandardButton.Discard:
            self.has_unsaved_changes = False
            return True
        else:  # Cancel
            return False
    
    def _nav_page(self, delta):
        """Navigate to previous/next page."""
        if not self._check_unsaved_changes():
            return
        
        current = self.file_combo.currentIndex()
        new_idx = current + delta
        if 0 <= new_idx < len(self.image_files):
            self.load_page(new_idx)
    
    # =========================================================================
    # DATA OPERATIONS
    # =========================================================================
    def save_json(self):
        """Save current data to JSON file avec vérification de cohérence."""
        if not self.current_json_path:
            return
        
        # Normaliser metadata et trier
        self.data = normalize_metadata(self.data)
        self.data = sort_json_structure_strictly(self.data)
        
        # Mettre à jour starts_at_ayah depuis le premier ayat numéroté
        self._update_starts_at_ayah()
        
        # Charger la page précédente pour comparaison
        prev_data = self._load_previous_page_data()
        
        # Vérifier cohérence
        errors, warnings = check_coherence(self.data, prev_data)
        
        # Afficher les erreurs/warnings si présents
        if errors or warnings:
            msg = ""
            if errors:
                msg += "❌ ERREURS:\n" + "\n".join(f"• {e}" for e in errors) + "\n\n"
            if warnings:
                msg += "⚠️ AVERTISSEMENTS:\n" + "\n".join(f"• {w}" for w in warnings)
            
            reply = QMessageBox.warning(
                self, 
                "Vérification de cohérence",
                msg + "\n\nVoulez-vous sauvegarder quand même?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                self.statusBar().showMessage("❌ Sauvegarde annulée")
                return
        
        # Sauvegarder
        os.makedirs(Config.JSON_DIR, exist_ok=True)
        with open(self.current_json_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        
        self.has_unsaved_changes = False
        self.statusBar().showMessage("✅ Sauvegardé!")

    def _upload_annotations_to_hf(self):
        """Uploader le dossier annotations vers Hugging Face."""
        if not HF_AVAILABLE:
            QMessageBox.warning(
                self, "HF non disponible",
                "huggingface_hub n'est pas installé.\npip install huggingface_hub"
            )
            return

        token = os.getenv("HUGGINGFACE_TOKEN")
        if not token:
            QMessageBox.warning(
                self, "Token manquant",
                "Définissez HUGGINGFACE_TOKEN dans le fichier .env"
            )
            return

        repo = os.getenv("HF_DATASET_REPO", "malekaidoudi/segment-quran-data")
        annotations_dir = Config.JSON_DIR

        if not os.path.exists(annotations_dir):
            QMessageBox.warning(self, "Dossier vide", f"Aucun dossier annotations trouvé:\n{annotations_dir}")
            return

        json_files = [f for f in os.listdir(annotations_dir) if f.endswith(".json")]
        if not json_files:
            QMessageBox.warning(self, "Aucun fichier", f"Aucun fichier JSON dans:\n{annotations_dir}")
            return

        reply = QMessageBox.question(
            self,
            "Confirmer l'upload",
            f"Uploader {len(json_files)} fichiers JSON vers Hugging Face?\n\n"
            f"Repo: {repo}\n"
            f"Dossier: annotations/\n\n"
            f"Cela peut prendre quelques minutes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                api = HfApi(token=token)
                upload_folder(
                    folder_path=annotations_dir,
                    path_in_repo="annotations",
                    repo_id=repo,
                    repo_type="dataset",
                )
                QMessageBox.information(
                    self, "Upload réussi",
                    f"✅ {len(json_files)} annotations uploadées!\n\n"
                    f"Votre collègue les verra au prochain lancement."
                )
                self.statusBar().showMessage("✅ Annotations uploadées sur HF")
            except Exception as e:
                QMessageBox.critical(self, "Erreur upload", str(e))

    def _update_starts_at_ayah(self):
        """Met à jour starts_at_ayah depuis le premier ayat numéroté."""
        ayats = self.data.get("ayats", [])
        for ayat in ayats:
            ayah_val = str(ayat.get("ayah", "1")).lower()
            if ayah_val != "basmala":
                surah = ayat.get("sourat_num", 1)
                try:
                    ayah = int(ayah_val)
                except ValueError:
                    ayah = 1
                self.data["metadata"]["starts_at_ayah"] = f"{surah}:{ayah}"
                break
    
    def _load_previous_page_data(self):
        """Charge les données de la page précédente pour comparaison."""
        page_num = self.data.get("metadata", {}).get("page", 1)
        prev_page = page_num - 1
        
        if prev_page < 1:
            return None
        
        for filename in os.listdir(Config.JSON_DIR) if os.path.exists(Config.JSON_DIR) else []:
            if not filename.endswith('.json'):
                continue
            match = re.search(r'(\d+)', filename)
            if match and int(match.group(1)) == prev_page:
                try:
                    with open(os.path.join(Config.JSON_DIR, filename), 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    pass
        
        return None
    
    def _save_state(self):
        """Save current state for undo."""
        self.history.append(copy.deepcopy(self.data))
        self.redo_stack.clear()
        if len(self.history) > 50:
            self.history.pop(0)
        self.has_unsaved_changes = True
    
    def undo(self):
        """Undo last change."""
        if self.history:
            self.redo_stack.append(copy.deepcopy(self.data))
            self.data = self.history.pop()
            self._refresh_all()
            self.statusBar().showMessage("↩ Annulé")
    
    def redo(self):
        """Redo last undone change."""
        if self.redo_stack:
            self.history.append(copy.deepcopy(self.data))
            self.data = self.redo_stack.pop()
            self._refresh_all()
            self.statusBar().showMessage("↪ Rétabli")
    
    def add_ayat(self):
        """Add new ayat entry."""
        self._save_state()
        
        # Determine next sourate/ayah and inherit division
        if self.data.get("ayats"):
            last = self.data["ayats"][-1]
            sourat = last.get("sourat_num", 1)
            ayah = last.get("ayah", "0")
            next_ayah = int(ayah) + 1 if str(ayah).isdigit() else 1
            division = last.get("division", "start")  # Hériter la division
        else:
            sourat = 1
            next_ayah = 1
            division = "start"
        
        self.data["ayats"].append({
            "sourat_num": sourat,
            "ayah": str(next_ayah),
            "division": division,  # Chaque ayat a sa division
            "rects": [{"line_idx": 1, "type": "Début", "coords": [200, 350, 800, 100]}]
        })
        
        self.focus_ayat = len(self.data["ayats"]) - 1
        self.focus_rect = 0
        self._refresh_all()
        self.statusBar().showMessage("➕ Ayat ajoutée")
    
    def add_polygon(self):
        """Add polygon to current ayat."""
        if self.focus_ayat >= len(self.data.get("ayats", [])):
            return
        
        self._save_state()
        
        ayat = self.data["ayats"][self.focus_ayat]
        rects = ayat.get("rects", [])
        
        # Base on last rect
        if rects:
            last = rects[-1]
            new_coords = [200, last["coords"][1] + 120, 800, 100]
            line_idx = last.get("line_idx", 0) + 1
        else:
            new_coords = [200, 350, 800, 100]
            line_idx = 1
        
        ayat["rects"].append({
            "line_idx": line_idx,
            "type": "Suite",
            "coords": new_coords
        })
        
        self.focus_rect = len(ayat["rects"]) - 1
        self._refresh_all()
        self.statusBar().showMessage("➕ Polygone ajouté")
    
    def delete_polygon(self):
        """Delete current polygon or ayat."""
        if self.focus_ayat >= len(self.data.get("ayats", [])):
            return
        
        self._save_state()
        
        ayat = self.data["ayats"][self.focus_ayat]
        if self.focus_rect < len(ayat.get("rects", [])):
            ayat["rects"].pop(self.focus_rect)
        
        # Remove ayat if no rects left
        if not ayat.get("rects"):
            self.data["ayats"].pop(self.focus_ayat)
            self.focus_ayat = max(0, self.focus_ayat - 1)
        
        self.focus_rect = 0
        self._refresh_all()
        self.statusBar().showMessage("🗑 Supprimé")
    
    def merge_polygon_to_previous(self):
        """Fusionne le polygone sélectionné avec l'ayat précédent.
        
        Cas d'usage: Le système de détection a créé une nouvelle ayat par erreur,
        mais le polygone est en réalité la continuation de l'ayat précédent.
        
        Logique:
        1. Prend le polygone actuellement sélectionné
        2. Vérifie si un polygone de l'ayat précédent est sur la même ligne:
           - Si OUI: étend le X du polygone précédent et supprime le polygone actuel
           - Si NON: déplace le polygone vers l'ayat précédent
        3. Si l'ayat actuel devient vide, le supprime et décale la numérotation
        """
        ayats = self.data.get("ayats", [])
        
        # Vérifier qu'on a au moins 2 ayats et que le focus n'est pas sur le premier
        if self.focus_ayat <= 0 or self.focus_ayat >= len(ayats):
            self.statusBar().showMessage("⚠ Impossible: pas d'ayat précédent")
            return
        
        current_ayat = ayats[self.focus_ayat]
        rects = current_ayat.get("rects", [])
        
        if self.focus_rect >= len(rects):
            self.statusBar().showMessage("⚠ Aucun polygone sélectionné")
            return
        
        self._save_state()
        
        # 1. Extraire le polygone sélectionné
        polygon_to_move = rects.pop(self.focus_rect)
        polygon_line = polygon_to_move.get("line_idx", -1)
        polygon_x = polygon_to_move["coords"][0]  # X du polygone à fusionner
        polygon_right = polygon_x + polygon_to_move["coords"][2]  # Bord droit
        
        # 2. Chercher un polygone de l'ayat précédent sur la même ligne
        prev_ayat = ayats[self.focus_ayat - 1]
        if "rects" not in prev_ayat:
            prev_ayat["rects"] = []
        
        same_line_poly = None
        for rect in prev_ayat["rects"]:
            if rect.get("line_idx", -1) == polygon_line:
                same_line_poly = rect
                break
        
        if same_line_poly is not None:
            # CAS: Même ligne → Étendre le polygone précédent vers la gauche
            prev_x = same_line_poly["coords"][0]
            prev_right = prev_x + same_line_poly["coords"][2]
            
            # Le nouveau X est le minimum (le plus à gauche)
            new_x = min(prev_x, polygon_x)
            # La nouvelle largeur couvre les deux polygones
            new_right = max(prev_right, polygon_right)
            new_w = new_right - new_x
            
            same_line_poly["coords"][0] = new_x
            same_line_poly["coords"][2] = new_w
            
            self.statusBar().showMessage(f"⬆ Polygone fusionné (même ligne): X={new_x}, W={new_w}")
        else:
            # CAS: Ligne différente → Ajouter le polygone à l'ayat précédent
            polygon_to_move["type"] = "Suite"
            prev_ayat["rects"].append(polygon_to_move)
            self.statusBar().showMessage("⬆ Polygone déplacé vers l'ayat précédent")
        
        # 3. Si l'ayat actuel n'a plus de polygones, le supprimer et décaler
        if not rects:
            removed_ayat = ayats.pop(self.focus_ayat)
            
            # 4. Décaler la numérotation des ayats suivants
            removed_ayah = str(removed_ayat.get("ayah", "")).lower()
            if removed_ayah != "basmala":
                for i in range(self.focus_ayat, len(ayats)):
                    ay = ayats[i]
                    ayah_val = str(ay.get("ayah", "1")).lower()
                    if ayah_val != "basmala":
                        try:
                            current_num = int(ayah_val)
                            ay["ayah"] = str(current_num - 1)
                        except ValueError:
                            pass
            
            self.focus_ayat = max(0, self.focus_ayat - 1)
        
        self.focus_rect = 0
        self.data = sort_json_structure_strictly(self.data)
        self._refresh_all()
    
    def merge_ayat_to_previous(self):
        """Fusionne tous les polygones de l'ayat actuel avec l'ayat précédent.
        
        Cas d'usage: Toute l'ayat actuelle est en fait une continuation de la précédente.
        
        Logique:
        1. Pour chaque polygone de l'ayat actuel:
           - Si même ligne qu'un polygone précédent: étendre le X
           - Sinon: déplacer le polygone
        2. Supprime l'ayat actuel
        3. Décale la numérotation des ayats suivants
        """
        ayats = self.data.get("ayats", [])
        
        # Vérifier qu'on a au moins 2 ayats et que le focus n'est pas sur le premier
        if self.focus_ayat <= 0 or self.focus_ayat >= len(ayats):
            self.statusBar().showMessage("⚠ Impossible: pas d'ayat précédent")
            return
        
        current_ayat = ayats[self.focus_ayat]
        rects_to_move = current_ayat.get("rects", [])
        
        if not rects_to_move:
            self.statusBar().showMessage("⚠ L'ayat actuel n'a pas de polygones")
            return
        
        self._save_state()
        
        # 1. Fusionner chaque polygone avec l'ayat précédent
        prev_ayat = ayats[self.focus_ayat - 1]
        if "rects" not in prev_ayat:
            prev_ayat["rects"] = []
        
        merged_count = 0
        moved_count = 0
        
        for poly in rects_to_move:
            poly_line = poly.get("line_idx", -1)
            poly_x = poly["coords"][0]
            poly_right = poly_x + poly["coords"][2]
            
            # Chercher un polygone de l'ayat précédent sur la même ligne
            same_line_poly = None
            for rect in prev_ayat["rects"]:
                if rect.get("line_idx", -1) == poly_line:
                    same_line_poly = rect
                    break
            
            if same_line_poly is not None:
                # Même ligne → Étendre le polygone précédent
                prev_x = same_line_poly["coords"][0]
                prev_right = prev_x + same_line_poly["coords"][2]
                
                new_x = min(prev_x, poly_x)
                new_right = max(prev_right, poly_right)
                new_w = new_right - new_x
                
                same_line_poly["coords"][0] = new_x
                same_line_poly["coords"][2] = new_w
                merged_count += 1
            else:
                # Ligne différente → Ajouter le polygone
                poly["type"] = "Suite"
                prev_ayat["rects"].append(poly)
                moved_count += 1
        
        # 2. Supprimer l'ayat actuel
        removed_ayat = ayats.pop(self.focus_ayat)
        
        # 3. Décaler la numérotation des ayats suivants
        removed_ayah = str(removed_ayat.get("ayah", "")).lower()
        if removed_ayah != "basmala":
            for i in range(self.focus_ayat, len(ayats)):
                ay = ayats[i]
                ayah_val = str(ay.get("ayah", "1")).lower()
                if ayah_val != "basmala":
                    try:
                        current_num = int(ayah_val)
                        ay["ayah"] = str(current_num - 1)
                    except ValueError:
                        pass
        
        self.focus_ayat = max(0, self.focus_ayat - 1)
        self.focus_rect = 0
        self.data = sort_json_structure_strictly(self.data)
        self._refresh_all()
        
        self.statusBar().showMessage(f"⬆⬆ {merged_count} fusionné(s) + {moved_count} déplacé(s)")
    
    def extract_basmala(self):
        """Extraire le polygone sélectionné comme Basmala.
        
        Logique:
        1. Prend le polygone actuellement sélectionné
        2. Copie son Y
        3. Supprime le polygone de l'ayat actuel
        4. Détermine le bon numéro de sourate via sommaire
        5. Crée un nouvel ayat "basmala" avec X=660, W=800, Y copié
        6. Corrige le numéro de sourate de tous les ayats suivants
        7. Place la basmala au début de la liste
        """
        if self.focus_ayat >= len(self.data.get("ayats", [])):
            self.statusBar().showMessage("⚠ Aucun polygone sélectionné")
            return
        
        ayat = self.data["ayats"][self.focus_ayat]
        rects = ayat.get("rects", [])
        
        if self.focus_rect >= len(rects):
            self.statusBar().showMessage("⚠ Aucun polygone sélectionné")
            return
        
        self._save_state()
        
        # 1. Copier Y du polygone sélectionné
        selected_rect = rects[self.focus_rect]
        y_copied = selected_rect["coords"][1]
        line_idx = selected_rect.get("line_idx", 1)
        old_sourat = ayat.get("sourat_num", 1)
        
        # 2. Déterminer le bon numéro de sourate
        # Basmala = nouvelle sourate, donc on vérifie avec le sommaire
        page_num = self.data.get("metadata", {}).get("page", 1)
        surahs_on_page = get_surah_for_page(page_num)
        
        # Si plusieurs sourates sur cette page, prendre la plus grande
        # (c'est la nouvelle sourate qui commence avec basmala)
        if surahs_on_page:
            new_sourat = max(surahs_on_page)
            # Vérifier que c'est bien une NOUVELLE sourate (pas sourate 9 qui n'a pas de basmala)
            if new_sourat == 9:
                new_sourat = old_sourat  # Pas de basmala pour sourate 9
        else:
            new_sourat = old_sourat + 1  # Fallback: sourate suivante
        
        # 3. Supprimer le polygone de l'ayat actuel
        rects.pop(self.focus_rect)
        
        # Si l'ayat n'a plus de polygones, le supprimer
        if not rects:
            self.data["ayats"].pop(self.focus_ayat)
        
        # 4. Corriger sourat_num pour tous les ayats de la nouvelle sourate
        # Les ayats après la position de basmala appartiennent à new_sourat
        basmala_line = line_idx
        for ay in self.data["ayats"]:
            # Si l'ayat a des rects sur ou après la ligne de basmala
            if ay.get("rects"):
                first_line = ay["rects"][0].get("line_idx", 999)
                if first_line >= basmala_line and ay.get("sourat_num") != new_sourat:
                    ay["sourat_num"] = new_sourat
        
        # 5. Créer le nouvel ayat basmala
        basmala_ayat = {
            "sourat_num": new_sourat,
            "ayah": "basmala",
            "rects": [{
                "line_idx": line_idx,
                "type": "Début",
                "coords": [660 if line_idx % 2 == 0 else 460, y_copied, 800, 100]
            }]
        }
        
        # 6. Insérer au début de la liste
        self.data["ayats"].insert(0, basmala_ayat)
        
        # Info sur la sourate
        nom_sourate = SOMMAIRE_DB.get(new_sourat, {}).get("nom", f"Sourate {new_sourat}")
        
        # 5. Focus sur la nouvelle basmala
        self.focus_ayat = 0
        self.focus_rect = 0
        
        self._refresh_all()
        self.statusBar().showMessage(f"☪ Basmala S{new_sourat} ({nom_sourate}) - Y={y_copied}")
    
    def _get_current_rect(self):
        """Get the currently focused rectangle."""
        if self.focus_ayat < len(self.data.get("ayats", [])):
            ayat = self.data["ayats"][self.focus_ayat]
            if self.focus_rect < len(ayat.get("rects", [])):
                return ayat["rects"][self.focus_rect]
        return None
    
    def _get_all_selected_rects(self):
        """Get all selected rectangles including focus."""
        rects = []
        
        # Current focus
        current = self._get_current_rect()
        if current:
            rects.append(current)
        
        # Multi-selected
        for a_idx, r_idx in self.selected_polygons:
            if a_idx < len(self.data.get("ayats", [])):
                ayat = self.data["ayats"][a_idx]
                if r_idx < len(ayat.get("rects", [])):
                    rect = ayat["rects"][r_idx]
                    if rect not in rects:
                        rects.append(rect)
        
        return rects
    
    def _find_ayat_idx_for_rect(self, rect):
        """Trouve l'index de l'ayat contenant un rectangle donné.
        
        Args:
            rect: Le rectangle à chercher
            
        Returns:
            int: Index de l'ayat ou -1 si non trouvé
        """
        for idx, ayat in enumerate(self.data.get("ayats", [])):
            if rect in ayat.get("rects", []):
                return idx
        return -1
    
    def _propagate_division(self, from_ayat_idx, division):
        """Propage une division à tous les ayats suivants et met à jour la basmala précédente si nécessaire.
        
        Args:
            from_ayat_idx: Index de l'ayat de départ
            division: La nouvelle division à appliquer
        """
        ayats = self.data.get("ayats", [])
        if from_ayat_idx < 0 or from_ayat_idx >= len(ayats):
            return
        
        # Mettre à jour cet ayat et tous les suivants
        for idx in range(from_ayat_idx, len(ayats)):
            ayats[idx]["division"] = division
        
        # Si c'est l'ayah 1, mettre à jour aussi la basmala précédente
        current_ayat = ayats[from_ayat_idx]
        if str(current_ayat.get("ayah", "")) == "1" and from_ayat_idx > 0:
            prev_ayat = ayats[from_ayat_idx - 1]
            if str(prev_ayat.get("ayah", "")).lower() == "basmala":
                prev_ayat["division"] = division
    
    def adjust_coord(self, coord, delta):
        """Adjust coordinate of all selected polygons."""
        rects = self._get_all_selected_rects()
        if not rects:
            return
        
        self._save_state()
        
        idx_map = {"x": 0, "y": 1, "w": 2, "h": 3}
        idx = idx_map.get(coord)
        
        if idx is not None:
            for rect in rects:
                coords = rect.get("coords", [0, 0, 100, 50])
                coords[idx] = max(0 if idx < 2 else 10, coords[idx] + delta)
        
        self._refresh_all()
        
        if len(rects) > 1:
            self.statusBar().showMessage(f"📐 {len(rects)} polygones modifiés")
    
    def apply_preset(self, name):
        """Apply preset coordinates."""
        rects = self._get_all_selected_rects()
        if not rects:
            return
        
        self._save_state()
        
        for rect in rects:
            coords = rect.get("coords", [0, 0, 100, 50])
            if name == "M1":
                coords[0], coords[2] = 385, 1314
                # Enlever le flag thumn si présent
                rect.pop("is_thumn", None)
            elif name == "M2":
                coords[0], coords[2] = 200, 1314
                # Enlever le flag thumn si présent
                rect.pop("is_thumn", None)
            elif name == "T3":
                # Vérifier si déjà marqué comme thumn (évite double réduction)
                if rect.get("is_thumn"):
                    self.statusBar().showMessage("⚠ Ce polygone est déjà marqué comme thumn")
                    continue
                
                # Réduire largeur de 80 et marquer comme thumn
                coords[2] = max(35, coords[2] - 80)
                rect["is_thumn"] = True
                
                # Passer à la division suivante et propager
                new_division = self._advance_division()
                ayat_idx = self._find_ayat_idx_for_rect(rect)
                self._propagate_division(ayat_idx, new_division)
        
        self._refresh_all()
        self.statusBar().showMessage(f"✨ Preset {name} appliqué")
    
    def reset_thumn(self):
        """Annule la marque thumn du polygone sélectionné et revient à la division précédente."""
        rects = self._get_all_selected_rects()
        if not rects:
            self.statusBar().showMessage("⚠ Aucun polygone sélectionné")
            return
        
        self._save_state()
        ayats = self.data.get("ayats", [])
        reset_count = 0
        
        for rect in rects:
            if rect.get("is_thumn"):
                # Restaurer la largeur (+80) et enlever le flag
                rect["coords"][2] += 80
                rect.pop("is_thumn", None)
                
                # Trouver l'ayat et restaurer la division précédente
                ayat_idx = self._find_ayat_idx_for_rect(rect)
                if ayat_idx >= 0:
                    prev_division = ayats[ayat_idx - 1].get("division", "start") if ayat_idx > 0 else "start"
                    self._propagate_division(ayat_idx, prev_division)
                
                reset_count += 1
                self._retreat_division()
        
        if reset_count > 0:
            self._refresh_all()
            self.statusBar().showMessage(f"↩ {reset_count} marque(s) thumn annulée(s)")
        else:
            self.statusBar().showMessage("⚠ Aucune marque thumn sur ce polygone")
    
    def _retreat_division(self):
        """Revient à la division précédente. start -> 7/8 avec hizb-1."""
        meta = self.data.get("metadata", {})
        current_hizb = meta.get("hizb", 1)
        current_juz = meta.get("juz", 1)
        
        div_order = ["start", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8"]
        
        # Trouver la dernière division assignée dans les ayats
        current_div = "start"
        for ayat in self.data.get("ayats", []):
            if "division" in ayat:
                current_div = ayat["division"]
        
        try:
            idx = div_order.index(current_div)
        except ValueError:
            idx = 0
        
        # Division précédente
        if idx == 0:  # start -> 7/8 du hizb précédent
            new_div = "7/8"
            new_hizb = max(1, current_hizb - 1)
            new_juz = (new_hizb - 1) // 2 + 1
        else:
            new_div = div_order[idx - 1]
            new_hizb = current_hizb
            new_juz = current_juz
        
        # Mettre à jour hizb/juz dans metadata
        self.data["metadata"]["hizb"] = new_hizb
        self.data["metadata"]["juz"] = new_juz
        
        # Mettre à jour les widgets
        self.hizb_spin.setValue(new_hizb)
        self.juz_spin.setValue(new_juz)
        
        self.statusBar().showMessage(
            f"↩ Division: {current_div} ← {new_div} | Hizb: {new_hizb} | Juz: {new_juz}"
        )
    
    def _advance_division(self):
        """Passe à la division suivante. 7/8 -> start avec hizb+1."""
        meta = self.data.get("metadata", {})
        current_hizb = meta.get("hizb", 1)
        current_juz = meta.get("juz", 1)
        
        # Trouver la dernière division assignée dans les ayats
        div_order = ["start", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8"]
        current_div = "start"
        
        for ayat in self.data.get("ayats", []):
            if "division" in ayat:
                current_div = ayat["division"]
        
        try:
            idx = div_order.index(current_div)
        except ValueError:
            idx = 0
        
        # Division suivante
        if idx == 7:  # 7/8 -> start + nouveau hizb
            new_div = "start"
            new_hizb = current_hizb + 1
            new_juz = (new_hizb - 1) // 2 + 1
        else:
            new_div = div_order[idx + 1]
            new_hizb = current_hizb
            new_juz = current_juz
        
        # Mettre à jour hizb/juz dans metadata (division n'est plus dans metadata)
        self.data["metadata"]["hizb"] = new_hizb
        self.data["metadata"]["juz"] = new_juz
        
        # Mettre à jour les widgets
        self.hizb_spin.setValue(new_hizb)
        self.juz_spin.setValue(new_juz)
        
        self.statusBar().showMessage(
            f"📊 Division: {current_div} → {new_div} | Hizb: {new_hizb} | Juz: {new_juz}"
        )
        
        return new_div
    
    # =========================================================================
    # DETECTION & ALIGNMENT
    # =========================================================================
    def run_detection(self):
        """Run auto-detection with current parameters - utilise process_page_v8_5."""
        if self.current_image is None:
            return
        
        self._save_state()
        
        self.statusBar().showMessage("🔍 Détection en cours...")
        QApplication.processEvents()
        
        # Extraire le numéro de page
        match = re.search(r'(\d+)', os.path.basename(self.current_image_path))
        page_num = int(match.group(1)) if match else 1
        
        base_sourat = self.base_sourat_spin.value()
        base_ayah = self.base_ayah_spin.value()
        
        # Utiliser le moteur v8.5 identique à l'app web
        v8_result = process_page_v8_5(
            self.current_image,
            self.pad_left_spin.value(),
            self.pad_right_spin.value(),
            self.start_y_spin.value(),
            self.line_h_spin.value(),
            Config.INTER_HEIGHT,
            Config.THRESHOLD,
            base_sourat,
            base_ayah
        )
        
        # Transformer en structure v18
        inherited_meta = self.data.get("metadata", {
            "juz": 1, "hizb": 1
        })
        
        self.data = transform_output_to_v18_structure(
            v8_result, page_num, base_sourat, base_ayah, inherited_meta
        )
        
        self._refresh_all()
        count = len(self.data.get("ayats", []))
        self.statusBar().showMessage(f"✅ {count} ayats détectées")
    
    def align_horizontal(self):
        """Ajustement horizontal - utilise LIGNE 1 comme référence pour toutes les autres."""
        if not self.data.get("ayats"):
            return
        
        self._save_state()
        
        # Grouper par ligne (exclure basmala)
        lines_map = {}
        for ayat in self.data["ayats"]:
            if str(ayat.get("ayah", "")).lower() == "basmala":
                continue
            for rect in ayat.get("rects", []):
                l_idx = int(rect.get("line_idx", 0))
                if l_idx not in lines_map:
                    lines_map[l_idx] = []
                lines_map[l_idx].append(rect)
        
        if not lines_map:
            return
        
        # Trouver la première ligne non-basmala comme référence
        min_line = min(lines_map.keys())
        ref_rects = lines_map[min_line]
        ref_rects.sort(key=lambda r: int(r["coords"][0]))
        
        # Calculer Xref et Xmax depuis ligne de référence
        Xref = ref_rects[0]["coords"][0]  # X du premier polygone (gauche)
        
        # Calculer Xmax en compensant les marques thumn (ajouter 80 si is_thumn)
        last_rect = ref_rects[-1]
        last_w = last_rect["coords"][2]
        if last_rect.get("is_thumn"):
            last_w += 80  # Compenser la réduction pour le calcul de référence
        Xmax = last_rect["coords"][0] + last_w  # Bord droit du dernier (compensé)
        Wref = Xmax - Xref
        
        # Appliquer l'alignement aux AUTRES lignes (ligne ref reste intacte)
        for l_idx, rects in lines_map.items():
            if l_idx == min_line:
                continue  # Ne pas modifier la ligne de référence
            
            rects.sort(key=lambda r: int(r["coords"][0]))  # Tri gauche à droite
            N = len(rects)
            
            if N == 1:
                # Un seul polygone: X=Xref, W=Wref
                rects[0]["coords"][0] = int(Xref)
                rects[0]["coords"][2] = int(Wref)
            else:
                # Premier polygone: ajuster X à Xref, garder bord droit fixe
                first = rects[0]
                old_right = first["coords"][0] + first["coords"][2]
                first["coords"][0] = int(Xref)
                first["coords"][2] = old_right - int(Xref)
                if first["coords"][2] < 35:
                    first["coords"][2] = 35
                
                # Dernier polygone: garder X, étendre W jusqu'à Xmax
                last = rects[-1]
                last["coords"][2] = int(Xmax) - last["coords"][0]
                if last["coords"][2] < 35:
                    last["coords"][2] = 35
        
        self.data = sort_json_structure_strictly(self.data)
        self._refresh_all()
        self.statusBar().showMessage(f"↔ Alignement H: Xref={Xref}, Xmax={Xmax}")
    
    def align_vertical(self):
        """Ajustement vertical - Y et H uniformes par ligne, exclut basmala."""
        if not self.data.get("ayats"):
            return
        
        self._save_state()
        
        # Grouper par ligne (exclure basmala)
        lines_map = {}
        for ayat in self.data["ayats"]:
            # Ignorer les lignes de basmala
            if str(ayat.get("ayah", "")).lower() == "basmala":
                continue
            for rect in ayat.get("rects", []):
                l_idx = int(rect.get("line_idx", 0))
                if l_idx not in lines_map:
                    lines_map[l_idx] = []
                lines_map[l_idx].append(rect)
        
        if not lines_map:
            return
        
        # Appliquer l'alignement par ligne
        for l_idx, rects in lines_map.items():
            rects.sort(key=lambda r: int(r["coords"][0]))  # Tri gauche à droite
            N = len(rects)
            
            if N == 1:
                # Si 1 seul polygone, forcer la hauteur à 105
                rects[0]["coords"][3] = 105
            else:
                # Si plusieurs, utiliser Y du premier (plus à gauche) et H=105 pour tous
                Yref = rects[0]["coords"][1]
                for rect in rects:
                    rect["coords"][1] = int(Yref)
                    rect["coords"][3] = 105
        
        self.data = sort_json_structure_strictly(self.data)
        self._refresh_all()
        self.statusBar().showMessage("↕ Alignement vertical appliqué")
    
    def align_all(self):
        """Apply both alignments."""
        self.align_horizontal()
        self.align_vertical()
        self.statusBar().showMessage("▣ Alignements H+V appliqués")
    
    # =========================================================================
    # UI UPDATES
    # =========================================================================
    def on_selection_changed(self):
        """Called when polygon selection changes."""
        self._update_properties()
        self.canvas.refresh()
        
        count = len(self.selected_polygons)
        if count > 0:
            self.statusBar().showMessage(f"🔶 {count + 1} polygones sélectionnés")
    
    def _refresh_all(self):
        """Refresh all UI elements."""
        self._update_ayat_list()
        self._update_properties()
        self.canvas.refresh()
    
    def _update_ayat_list(self):
        """Update the ayat tree widget with hierarchical structure."""
        self.ayat_tree.blockSignals(True)
        self.ayat_tree.clear()
        
        # Update group title with count
        count = len(self.data.get("ayats", []))
        self.ayat_group.setTitle(f"Ayats détectées ({count})")
        
        for ayat_idx, ayat in enumerate(self.data.get("ayats", [])):
            sourat = ayat.get("sourat_num", "?")
            ayah = ayat.get("ayah", "?")
            rects = ayat.get("rects", [])
            
            # Get surah name (surah_db = {number: nameAr})
            name = ""
            if sourat in self.surah_db:
                name = f" - {self.surah_db[sourat]}"
            
            # Create ayat item
            ayat_text = f"S{sourat} A{ayah}{name} ({len(rects)})"
            ayat_item = QTreeWidgetItem([ayat_text])
            ayat_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "ayat", "index": ayat_idx})
            
            # Add polygon sub-items
            for rect_idx, rect in enumerate(rects):
                coords = rect.get("coords", [0, 0, 0, 0])
                line_idx = rect.get("line_idx", "?")
                rect_type = rect.get("type", "?")
                poly_text = f"  L{line_idx} [{rect_type}] ({coords[0]},{coords[1]} {coords[2]}x{coords[3]})"
                poly_item = QTreeWidgetItem([poly_text])
                poly_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "polygon", "ayat_idx": ayat_idx, "rect_idx": rect_idx})
                ayat_item.addChild(poly_item)
            
            self.ayat_tree.addTopLevelItem(ayat_item)
        
        # Restore selection
        if self.focus_ayat < self.ayat_tree.topLevelItemCount():
            item = self.ayat_tree.topLevelItem(self.focus_ayat)
            self.ayat_tree.setCurrentItem(item)
            if self.focus_rect >= 0 and item.childCount() > self.focus_rect:
                item.setExpanded(True)
                self.ayat_tree.setCurrentItem(item.child(self.focus_rect))
        
        self.ayat_tree.blockSignals(False)
    
    def _update_properties(self):
        """Update property panel with current selection."""
        widgets = [
            self.sourat_spin, self.ayah_spin,
            self.x_spin, self.y_spin, self.w_spin, self.h_spin,
            self.juz_spin, self.hizb_spin, self.line_idx_spin
        ]
        
        for w in widgets:
            w.blockSignals(True)
        self.basmala_check.blockSignals(True)
        self.sajda_check.blockSignals(True)
        self.division_combo.blockSignals(True)
        
        # Metadata
        self.starts_at_edit.blockSignals(True)
        
        meta = self.data.get("metadata", {})
        self.juz_spin.setValue(meta.get("juz", 1))
        self.hizb_spin.setValue(meta.get("hizb", 1))
        
        self.starts_at_edit.setText(meta.get("starts_at_ayah", ""))
        
        self.starts_at_edit.blockSignals(False)
        
        # Current ayat/rect
        if self.focus_ayat < len(self.data.get("ayats", [])):
            ayat = self.data["ayats"][self.focus_ayat]
            self.sourat_spin.setValue(ayat.get("sourat_num", 1))
            
            # Handle basmala
            ayah_value = ayat.get("ayah", "1")
            if str(ayah_value).lower() == "basmala":
                self.basmala_check.setChecked(True)
                self.ayah_spin.setEnabled(False)
                self.ayah_spin.setValue(0)
            else:
                self.basmala_check.setChecked(False)
                self.ayah_spin.setEnabled(True)
                try:
                    self.ayah_spin.setValue(int(ayah_value))
                except:
                    self.ayah_spin.setValue(0)
            
            rect = self._get_current_rect()
            if rect:
                coords = rect.get("coords", [0, 0, 100, 50])
                self.x_spin.setValue(coords[0])
                self.y_spin.setValue(coords[1])
                self.w_spin.setValue(coords[2])
                self.h_spin.setValue(coords[3])
                self.line_idx_spin.setValue(rect.get("line_idx", 1))
            
            # Sajda
            self.sajda_check.setChecked(ayat.get("sajda", False))
            
            # Division de l'ayat
            division = ayat.get("division", "start")
            idx = self.division_combo.findText(division)
            if idx >= 0:
                self.division_combo.setCurrentIndex(idx)
        
        self.basmala_check.blockSignals(False)
        self.sajda_check.blockSignals(False)
        self.division_combo.blockSignals(False)
        for w in widgets:
            w.blockSignals(False)
    
    def _on_tree_item_clicked(self, item, column):
        """Handle tree item click - select ayat or polygon."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        self.selected_polygons = []
        
        if data["type"] == "ayat":
            self.focus_ayat = data["index"]
            self.focus_rect = 0
        elif data["type"] == "polygon":
            self.focus_ayat = data["ayat_idx"]
            self.focus_rect = data["rect_idx"]
        
        self._update_properties()
        self.canvas.refresh()
    
    def _on_tree_item_expanded(self, item):
        """Handle tree item expansion."""
        pass  # Nothing special needed
    
    def _on_basmala_toggled(self, checked):
        """Handle basmala checkbox toggle."""
        if self.focus_ayat < len(self.data.get("ayats", [])):
            if checked:
                self.data["ayats"][self.focus_ayat]["ayah"] = "basmala"
                self.ayah_spin.setEnabled(False)
                
                # Auto-définir x selon la parité de la page
                page_num = self.data.get("metadata", {}).get("page", 1)
                expected_x = 660 if (page_num % 2 == 0) else 460
                rects = self.data["ayats"][self.focus_ayat].get("rects", [])
                for rect in rects:
                    coords = rect.get("coords", [])
                    if coords and len(coords) >= 1:
                        coords[0] = expected_x
                self._update_properties()
            else:
                self.data["ayats"][self.focus_ayat]["ayah"] = str(self.ayah_spin.value())
                self.ayah_spin.setEnabled(True)
            self._update_ayat_list()
    
    def _on_sajda_toggled(self, checked):
        """Handle sajda checkbox toggle."""
        if self.focus_ayat < len(self.data.get("ayats", [])):
            self._save_state()
            if checked:
                self.data["ayats"][self.focus_ayat]["sajda"] = True
            else:
                # Supprimer la clé si False pour garder le JSON propre
                self.data["ayats"][self.focus_ayat].pop("sajda", None)
            self.has_unsaved_changes = True
            self._update_ayat_list()
            self.statusBar().showMessage(f"🕌 Sajda: {'Oui' if checked else 'Non'}")
    
    def _on_division_changed(self, division):
        """Handle division combo change - met à jour l'ayat sélectionné et tous les suivants."""
        if self.focus_ayat >= len(self.data.get("ayats", [])):
            return
        
        self._save_state()
        self._propagate_division(self.focus_ayat, division)
        
        self.has_unsaved_changes = True
        self._update_ayat_list()
        self.statusBar().showMessage(f"📊 Division mise à jour: {division}")
    
    def _on_line_idx_changed(self, value):
        """Handle line index spinbox change."""
        rect = self._get_current_rect()
        if rect:
            self._save_state()
            rect["line_idx"] = value
            self.has_unsaved_changes = True
            self._update_ayat_list()
            self.canvas.update()
            self.statusBar().showMessage(f"📍 Ligne mise à jour: L{value}")
    
    def _on_sourat_changed(self, value):
        """Handle sourate spinbox change avec correction automatique."""
        if self.focus_ayat >= len(self.data.get("ayats", [])):
            return
        
        self._save_state()
        self.data["ayats"][self.focus_ayat]["sourat_num"] = value
        
        # Si c'est le premier ayat (non-basmala), propager la correction
        if self._is_first_numbered_ayat():
            self._auto_correct_sequence()
        
        self._update_ayat_list()
    
    def _on_ayah_changed(self, value):
        """Handle ayah spinbox change avec correction automatique."""
        if self.focus_ayat >= len(self.data.get("ayats", [])):
            return
        
        self._save_state()
        self.data["ayats"][self.focus_ayat]["ayah"] = str(value)
        
        # Si c'est le premier ayat (non-basmala), propager la correction
        if self._is_first_numbered_ayat():
            self._auto_correct_sequence()
        
        self._update_ayat_list()
    
    def _is_first_numbered_ayat(self):
        """Vérifie si l'ayat actuellement sélectionné est le premier ayat numéroté (non-basmala)."""
        for i, ayat in enumerate(self.data.get("ayats", [])):
            ayah_val = str(ayat.get("ayah", "1")).lower()
            if ayah_val != "basmala":
                return i == self.focus_ayat
        return False
    
    def _auto_correct_sequence(self):
        """Corrige automatiquement la séquence de tous les ayats après le premier.
        
        Utilise sommaire.csv pour vérifier le nombre d'ayats par sourate.
        Quand un ayat dépasse le total, passe à la sourate suivante.
        """
        ayats = self.data.get("ayats", [])
        if not ayats:
            return
        
        # Trouver le premier ayat numéroté et son numéro
        start_idx = -1
        current_surah = 1
        current_ayah = 1
        
        for i, ayat in enumerate(ayats):
            ayah_val = str(ayat.get("ayah", "1")).lower()
            if ayah_val != "basmala":
                start_idx = i
                current_surah = int(ayat.get("sourat_num", 1))
                try:
                    current_ayah = int(ayah_val)
                except ValueError:
                    current_ayah = 1
                break
        
        if start_idx < 0:
            return
        
        # Récupérer le total d'ayats pour la sourate courante
        total_ayats = SOMMAIRE_DB.get(current_surah, {}).get("total_ayats", 999)
        
        # Parcourir tous les ayats APRÈS le premier et les corriger
        for i in range(start_idx + 1, len(ayats)):
            ayat = ayats[i]
            ayah_val = str(ayat.get("ayah", "1")).lower()
            
            # Skip basmala
            if ayah_val == "basmala":
                continue
            
            # Incrémenter ayah
            current_ayah += 1
            
            # Vérifier si on dépasse le total → nouvelle sourate
            if current_ayah > total_ayats:
                current_surah += 1
                current_ayah = 1
                total_ayats = SOMMAIRE_DB.get(current_surah, {}).get("total_ayats", 999)
                
                # Ajouter basmala automatiquement si nécessaire (sauf sourate 9)
                # Note: la basmala devrait déjà être présente si détectée
            
            # Mettre à jour l'ayat
            ayat["sourat_num"] = current_surah
            ayat["ayah"] = str(current_ayah)
        
        # Mettre à jour les metadata avec le nouveau format "S:A"
        if start_idx == 0 or (start_idx == 1 and str(ayats[0].get("ayah", "")).lower() == "basmala"):
            first_ayat = ayats[start_idx]
            s = first_ayat.get("sourat_num", 1)
            a = first_ayat.get("ayah", "1")
            self.data["metadata"]["starts_at_ayah"] = f"{s}:{a}"
        
        self.statusBar().showMessage(f"✅ Séquence corrigée: S{current_surah} jusqu'à A{current_ayah}")
    
    def _manual_correct_sequence(self):
        """Déclenche manuellement la correction de séquence."""
        if not self.data.get("ayats"):
            self.statusBar().showMessage("⚠ Aucun ayat à corriger")
            return
        
        self._save_state()
        self._auto_correct_sequence()
        self._update_ayat_list()
        self.canvas.refresh()
    
    def _on_coords_changed(self):
        """Handle coordinate spinbox changes."""
        rect = self._get_current_rect()
        if rect:
            rect["coords"] = [
                self.x_spin.value(),
                self.y_spin.value(),
                self.w_spin.value(),
                self.h_spin.value()
            ]
            self.canvas.refresh()
    
    def _on_meta_changed(self):
        """Handle metadata changes."""
        if "metadata" not in self.data:
            self.data["metadata"] = {}
        
        self.data["metadata"]["juz"] = self.juz_spin.value()
        self.data["metadata"]["hizb"] = self.hizb_spin.value()
        self.data["metadata"]["starts_at_ayah"] = self.starts_at_edit.text() or "1:1"
    
    def _adjust_by_step(self, key):
        """Adjust coordinate using step values."""
        rect = self._get_current_rect()
        if not rect:
            return
        
        self._save_state()
        coords = rect.get("coords", [0, 0, 100, 50])
        
        step_x = self.step_x_spin.value()
        step_w = self.step_w_spin.value()
        
        if key == "x-":
            # X diminue, W augmente (bord droit reste fixe)
            coords[0] -= step_x
            coords[2] += step_x
        elif key == "x+":
            # X augmente, W diminue (bord droit reste fixe)
            coords[0] += step_x
            coords[2] -= step_x
            if coords[2] < 35:
                coords[2] = 35
        elif key == "y-":
            coords[1] -= 10
        elif key == "y+":
            coords[1] += 10
        elif key == "w-":
            coords[2] -= step_w
        elif key == "w+":
            coords[2] += step_w
        elif key == "h-":
            coords[3] -= 5
        elif key == "h+":
            coords[3] += 5
        
        rect["coords"] = coords
        self._update_properties()
        self.canvas.refresh()
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts including Shift+Arrow."""
        key = event.key()
        modifiers = event.modifiers()
        
        rect = self._get_current_rect()
        if not rect:
            super().keyPressEvent(event)
            return
        
        coords = rect.get("coords", [0, 0, 100, 50])
        step = 5 if modifiers & Qt.KeyboardModifier.ShiftModifier else 1
        changed = False
        
        if key == Qt.Key.Key_Left:
            coords[0] -= step
            changed = True
        elif key == Qt.Key.Key_Right:
            coords[0] += step
            changed = True
        elif key == Qt.Key.Key_Up:
            coords[1] -= step
            changed = True
        elif key == Qt.Key.Key_Down:
            coords[1] += step
            changed = True
        
        if changed:
            self._save_state()
            rect["coords"] = coords
            self._update_properties()
            self.canvas.refresh()
        else:
            super().keyPressEvent(event)


# =============================================================================
# MAIN
# =============================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    
    window = QuranEditor()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    data_manager.ensure_data()
    main()
