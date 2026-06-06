#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quran Ayat Editor - Version Responsive & Universelle
Application installable pour Mac/Windows
Supporte n'importe quel Mushaf avec configuration personnalisée
"""

import os
import sys
import json
import re
import copy
import hashlib
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QLineEdit, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QSplitter, QScrollArea, QFrame,
    QFileDialog, QMessageBox, QStatusBar, QGroupBox,
    QGridLayout, QSizePolicy, QMenu, QMenuBar, QDialog, QTabWidget,
    QFormLayout, QCheckBox, QDialogButtonBox, QToolBar, QStyle,
    QListWidget, QListWidgetItem, QProgressDialog
)
from PyQt6.QtCore import Qt, QSettings, QSize, QTimer
from PyQt6.QtGui import QImage, QPixmap, QKeySequence, QAction, QIcon, QFont, QShortcut


# =============================================================================
# CONFIGURATION - Paramètres par défaut modifiables
# =============================================================================
class AppConfig:
    """Configuration globale de l'application - sauvegardée dans QSettings."""
    
    # Valeurs par défaut
    DEFAULTS = {
        # Chemins
        "image_dir": "",
        "json_dir": "",
        "sommaire_file": "",
        "samples_dir": "",
        
        # Échantillons
        "sample_surah_header": "",
        "sample_ayat_mark": "",
        "sample_thumn_mark": "",
        
        # Division mode
        "division_mode": "1/8",  # "1/8" ou "1/4"
        
        # Padding détection
        "padding_left_odd": 35,
        "padding_right_odd": 110,
        "padding_left_even": 110,
        "padding_right_even": 35,
        
        # Interface
        "theme": "light",
        "font_size": 12,
        "auto_save": False,
        "show_overlay": True,
        "overlay_opacity": 0.4,
        
        # Fenêtre
        "window_geometry": None,
        "splitter_state": None,
    }
    
    def __init__(self):
        self.settings = QSettings("QuranEditor", "ResponsiveApp")
        self._cache = {}
        self._load_all()
    
    def _load_all(self):
        """Charge tous les paramètres."""
        for key, default in self.DEFAULTS.items():
            self._cache[key] = self.settings.value(key, default)
    
    def get(self, key):
        """Récupère une valeur."""
        return self._cache.get(key, self.DEFAULTS.get(key))
    
    def set(self, key, value):
        """Définit une valeur."""
        self._cache[key] = value
        self.settings.setValue(key, value)
    
    def get_divisions(self):
        """Retourne la liste des divisions selon le mode."""
        if self.get("division_mode") == "1/4":
            return ["start", "1/4", "1/2", "3/4"]
        else:
            return ["start", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8"]


# Instance globale
CONFIG = AppConfig()


# =============================================================================
# BASE DE DONNÉES - Sourates et Sommaire
# =============================================================================
SURAH_DB = {}
SOMMAIRE_DB = {}


def load_surah_database():
    """Charge la base des noms de sourates."""
    global SURAH_DB
    SURAH_DB = {
        1: "Al-Fatiha", 2: "Al-Baqara", 3: "Al-Imran", 4: "An-Nisa",
        5: "Al-Ma'ida", 6: "Al-An'am", 7: "Al-A'raf", 8: "Al-Anfal",
        9: "At-Tawba", 10: "Yunus", 11: "Hud", 12: "Yusuf",
        13: "Ar-Ra'd", 14: "Ibrahim", 15: "Al-Hijr", 16: "An-Nahl",
        17: "Al-Isra", 18: "Al-Kahf", 19: "Maryam", 20: "Ta-Ha",
        21: "Al-Anbiya", 22: "Al-Hajj", 23: "Al-Mu'minun", 24: "An-Nur",
        25: "Al-Furqan", 26: "Ash-Shu'ara", 27: "An-Naml", 28: "Al-Qasas",
        29: "Al-Ankabut", 30: "Ar-Rum", 31: "Luqman", 32: "As-Sajda",
        33: "Al-Ahzab", 34: "Saba", 35: "Fatir", 36: "Ya-Sin",
        37: "As-Saffat", 38: "Sad", 39: "Az-Zumar", 40: "Ghafir",
        41: "Fussilat", 42: "Ash-Shura", 43: "Az-Zukhruf", 44: "Ad-Dukhan",
        45: "Al-Jathiya", 46: "Al-Ahqaf", 47: "Muhammad", 48: "Al-Fath",
        49: "Al-Hujurat", 50: "Qaf", 51: "Adh-Dhariyat", 52: "At-Tur",
        53: "An-Najm", 54: "Al-Qamar", 55: "Ar-Rahman", 56: "Al-Waqi'a",
        57: "Al-Hadid", 58: "Al-Mujadila", 59: "Al-Hashr", 60: "Al-Mumtahina",
        61: "As-Saff", 62: "Al-Jumu'a", 63: "Al-Munafiqun", 64: "At-Taghabun",
        65: "At-Talaq", 66: "At-Tahrim", 67: "Al-Mulk", 68: "Al-Qalam",
        69: "Al-Haqqa", 70: "Al-Ma'arij", 71: "Nuh", 72: "Al-Jinn",
        73: "Al-Muzzammil", 74: "Al-Muddaththir", 75: "Al-Qiyama", 76: "Al-Insan",
        77: "Al-Mursalat", 78: "An-Naba", 79: "An-Nazi'at", 80: "Abasa",
        81: "At-Takwir", 82: "Al-Infitar", 83: "Al-Mutaffifin", 84: "Al-Inshiqaq",
        85: "Al-Buruj", 86: "At-Tariq", 87: "Al-A'la", 88: "Al-Ghashiya",
        89: "Al-Fajr", 90: "Al-Balad", 91: "Ash-Shams", 92: "Al-Layl",
        93: "Ad-Duha", 94: "Ash-Sharh", 95: "At-Tin", 96: "Al-Alaq",
        97: "Al-Qadr", 98: "Al-Bayyina", 99: "Az-Zalzala", 100: "Al-Adiyat",
        101: "Al-Qari'a", 102: "At-Takathur", 103: "Al-Asr", 104: "Al-Humaza",
        105: "Al-Fil", 106: "Quraysh", 107: "Al-Ma'un", 108: "Al-Kawthar",
        109: "Al-Kafirun", 110: "An-Nasr", 111: "Al-Masad", 112: "Al-Ikhlas",
        113: "Al-Falaq", 114: "An-Nas"
    }
    return SURAH_DB


def load_sommaire(filepath=None):
    """Charge le sommaire depuis un fichier CSV."""
    global SOMMAIRE_DB
    SOMMAIRE_DB = {}
    
    if not filepath:
        filepath = CONFIG.get("sommaire_file")
    
    if not filepath or not os.path.exists(filepath):
        # Chercher le fichier par défaut
        default_path = os.path.join(os.path.dirname(__file__), "data", "sommaire.csv")
        if os.path.exists(default_path):
            filepath = default_path
        else:
            return SOMMAIRE_DB
    
    try:
        df = pd.read_csv(filepath)
        for _, row in df.iterrows():
            SOMMAIRE_DB[int(row['Sourate_Num'])] = {
                "page": int(row['Page']),
                "total_ayats": int(row['Total_Ayats']),
                "nom": row['Nom']
            }
    except Exception as e:
        print(f"Erreur chargement sommaire: {e}")
    
    return SOMMAIRE_DB


def get_surah_for_page(page_num):
    """Retourne la sourate principale pour une page."""
    if not SOMMAIRE_DB:
        return 1
    
    sorted_surahs = sorted(SOMMAIRE_DB.items(), key=lambda x: x[1]["page"])
    current_surah = 1
    
    for s_num, info in sorted_surahs:
        if info["page"] <= page_num:
            current_surah = s_num
        else:
            break
    
    return current_surah


def estimate_metadata_for_page(page_num):
    """Estime les métadonnées pour une page donnée."""
    if page_num <= 1:
        return {"juz": 1, "hizb": 1, "division": "start", "surah": 1, "ayah": 1}
    
    divisions = CONFIG.get_divisions()
    pages_per_hizb = 10
    divs_per_hizb = len(divisions)
    
    juz = min(30, max(1, ((page_num - 2) // 20) + 1))
    hizb = min(60, max(1, ((page_num - 2) // pages_per_hizb) + 1))
    
    page_in_hizb = (page_num - 2) % pages_per_hizb
    div_idx = min(len(divisions) - 1, int(page_in_hizb * divs_per_hizb / pages_per_hizb))
    division = divisions[div_idx]
    
    surah = get_surah_for_page(page_num)
    ayah = 1
    
    if surah in SOMMAIRE_DB:
        start_page = SOMMAIRE_DB[surah]["page"]
        total_ayats = SOMMAIRE_DB[surah]["total_ayats"]
        pages_into_surah = page_num - start_page
        ayah = min(total_ayats, max(1, pages_into_surah * 15 + 1))
    
    return {
        "juz": juz, "hizb": hizb, "division": division,
        "surah": surah, "ayah": ayah,
        "division_anchor_ayah": f"{surah}:{ayah}"
    }


# =============================================================================
# DIALOGUE DE PARAMÈTRES
# =============================================================================
class SettingsDialog(QDialog):
    """Dialogue de configuration de l'application."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres")
        self.setMinimumSize(600, 500)
        self._setup_ui()
        self._load_values()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Tabs
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # === Tab Projet ===
        project_tab = QWidget()
        project_layout = QFormLayout(project_tab)
        
        # Dossier images
        self.image_dir_edit = QLineEdit()
        image_dir_btn = QPushButton("Parcourir...")
        image_dir_btn.clicked.connect(lambda: self._browse_dir(self.image_dir_edit))
        img_layout = QHBoxLayout()
        img_layout.addWidget(self.image_dir_edit)
        img_layout.addWidget(image_dir_btn)
        project_layout.addRow("Dossier images:", img_layout)
        
        # Dossier JSON
        self.json_dir_edit = QLineEdit()
        json_dir_btn = QPushButton("Parcourir...")
        json_dir_btn.clicked.connect(lambda: self._browse_dir(self.json_dir_edit))
        json_layout = QHBoxLayout()
        json_layout.addWidget(self.json_dir_edit)
        json_layout.addWidget(json_dir_btn)
        project_layout.addRow("Dossier annotations:", json_layout)
        
        # Fichier sommaire
        self.sommaire_edit = QLineEdit()
        sommaire_btn = QPushButton("Parcourir...")
        sommaire_btn.clicked.connect(lambda: self._browse_file(self.sommaire_edit, "CSV (*.csv)"))
        som_layout = QHBoxLayout()
        som_layout.addWidget(self.sommaire_edit)
        som_layout.addWidget(sommaire_btn)
        project_layout.addRow("Fichier sommaire:", som_layout)
        
        tabs.addTab(project_tab, "Projet")
        
        # === Tab Échantillons ===
        samples_tab = QWidget()
        samples_layout = QFormLayout(samples_tab)
        
        self.sample_header_edit = QLineEdit()
        header_btn = QPushButton("Parcourir...")
        header_btn.clicked.connect(lambda: self._browse_file(self.sample_header_edit, "Images (*.png *.jpg)"))
        header_layout = QHBoxLayout()
        header_layout.addWidget(self.sample_header_edit)
        header_layout.addWidget(header_btn)
        samples_layout.addRow("En-tête sourate:", header_layout)
        
        self.sample_ayat_edit = QLineEdit()
        ayat_btn = QPushButton("Parcourir...")
        ayat_btn.clicked.connect(lambda: self._browse_file(self.sample_ayat_edit, "Images (*.png *.jpg)"))
        ayat_layout = QHBoxLayout()
        ayat_layout.addWidget(self.sample_ayat_edit)
        ayat_layout.addWidget(ayat_btn)
        samples_layout.addRow("Marque ayat:", ayat_layout)
        
        self.sample_thumn_edit = QLineEdit()
        thumn_btn = QPushButton("Parcourir...")
        thumn_btn.clicked.connect(lambda: self._browse_file(self.sample_thumn_edit, "Images (*.png *.jpg)"))
        thumn_layout = QHBoxLayout()
        thumn_layout.addWidget(self.sample_thumn_edit)
        thumn_layout.addWidget(thumn_btn)
        samples_layout.addRow("Marque thumn:", thumn_layout)
        
        tabs.addTab(samples_tab, "Échantillons")
        
        # === Tab Détection ===
        detection_tab = QWidget()
        detection_layout = QFormLayout(detection_tab)
        
        self.division_combo = QComboBox()
        self.division_combo.addItems(["1/8 (8 divisions)", "1/4 (4 divisions)"])
        detection_layout.addRow("Mode division:", self.division_combo)
        
        self.pad_left_odd = QSpinBox()
        self.pad_left_odd.setRange(0, 500)
        detection_layout.addRow("Padding gauche (impair):", self.pad_left_odd)
        
        self.pad_right_odd = QSpinBox()
        self.pad_right_odd.setRange(0, 500)
        detection_layout.addRow("Padding droit (impair):", self.pad_right_odd)
        
        self.pad_left_even = QSpinBox()
        self.pad_left_even.setRange(0, 500)
        detection_layout.addRow("Padding gauche (pair):", self.pad_left_even)
        
        self.pad_right_even = QSpinBox()
        self.pad_right_even.setRange(0, 500)
        detection_layout.addRow("Padding droit (pair):", self.pad_right_even)
        
        tabs.addTab(detection_tab, "Détection")
        
        # === Tab Interface ===
        ui_tab = QWidget()
        ui_layout = QFormLayout(ui_tab)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Clair", "Sombre"])
        ui_layout.addRow("Thème:", self.theme_combo)
        
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 20)
        ui_layout.addRow("Taille police:", self.font_spin)
        
        self.auto_save_check = QCheckBox("Sauvegarder automatiquement")
        ui_layout.addRow("", self.auto_save_check)
        
        self.overlay_check = QCheckBox("Afficher les overlays")
        ui_layout.addRow("", self.overlay_check)
        
        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(10, 100)
        self.opacity_spin.setSuffix("%")
        ui_layout.addRow("Opacité overlay:", self.opacity_spin)
        
        tabs.addTab(ui_tab, "Interface")
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._restore_defaults)
        layout.addWidget(buttons)
    
    def _browse_dir(self, line_edit):
        path = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
        if path:
            line_edit.setText(path)
    
    def _browse_file(self, line_edit, filter_str):
        path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un fichier", "", filter_str)
        if path:
            line_edit.setText(path)
    
    def _load_values(self):
        self.image_dir_edit.setText(CONFIG.get("image_dir") or "")
        self.json_dir_edit.setText(CONFIG.get("json_dir") or "")
        self.sommaire_edit.setText(CONFIG.get("sommaire_file") or "")
        
        self.sample_header_edit.setText(CONFIG.get("sample_surah_header") or "")
        self.sample_ayat_edit.setText(CONFIG.get("sample_ayat_mark") or "")
        self.sample_thumn_edit.setText(CONFIG.get("sample_thumn_mark") or "")
        
        div_mode = CONFIG.get("division_mode")
        self.division_combo.setCurrentIndex(0 if div_mode == "1/8" else 1)
        
        self.pad_left_odd.setValue(CONFIG.get("padding_left_odd") or 35)
        self.pad_right_odd.setValue(CONFIG.get("padding_right_odd") or 110)
        self.pad_left_even.setValue(CONFIG.get("padding_left_even") or 110)
        self.pad_right_even.setValue(CONFIG.get("padding_right_even") or 35)
        
        theme = CONFIG.get("theme")
        self.theme_combo.setCurrentIndex(0 if theme == "light" else 1)
        self.font_spin.setValue(CONFIG.get("font_size") or 12)
        self.auto_save_check.setChecked(CONFIG.get("auto_save") or False)
        self.overlay_check.setChecked(CONFIG.get("show_overlay") if CONFIG.get("show_overlay") is not None else True)
        self.opacity_spin.setValue(int((CONFIG.get("overlay_opacity") or 0.4) * 100))
    
    def _save_and_accept(self):
        CONFIG.set("image_dir", self.image_dir_edit.text())
        CONFIG.set("json_dir", self.json_dir_edit.text())
        CONFIG.set("sommaire_file", self.sommaire_edit.text())
        
        CONFIG.set("sample_surah_header", self.sample_header_edit.text())
        CONFIG.set("sample_ayat_mark", self.sample_ayat_edit.text())
        CONFIG.set("sample_thumn_mark", self.sample_thumn_edit.text())
        
        CONFIG.set("division_mode", "1/8" if self.division_combo.currentIndex() == 0 else "1/4")
        
        CONFIG.set("padding_left_odd", self.pad_left_odd.value())
        CONFIG.set("padding_right_odd", self.pad_right_odd.value())
        CONFIG.set("padding_left_even", self.pad_left_even.value())
        CONFIG.set("padding_right_even", self.pad_right_even.value())
        
        CONFIG.set("theme", "light" if self.theme_combo.currentIndex() == 0 else "dark")
        CONFIG.set("font_size", self.font_spin.value())
        CONFIG.set("auto_save", self.auto_save_check.isChecked())
        CONFIG.set("show_overlay", self.overlay_check.isChecked())
        CONFIG.set("overlay_opacity", self.opacity_spin.value() / 100)
        
        self.accept()
    
    def _restore_defaults(self):
        for key, value in AppConfig.DEFAULTS.items():
            CONFIG.set(key, value)
        self._load_values()


# =============================================================================
# DIALOGUE À PROPOS
# =============================================================================
class AboutDialog(QDialog):
    """Dialogue À propos."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("À propos")
        self.setFixedSize(400, 300)
        
        layout = QVBoxLayout(self)
        
        title = QLabel("Quran Ayat Editor")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        version = QLabel("Version 2.0 - Responsive")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        
        desc = QLabel(
            "Application universelle pour la segmentation\n"
            "et l'annotation des pages du Coran.\n\n"
            "Supporte n'importe quel Mushaf avec\n"
            "configuration personnalisée."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)
        
        layout.addStretch()
        
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# =============================================================================
# CANVAS WIDGET - Zone d'affichage de l'image
# =============================================================================
class CanvasWidget(QLabel):
    """Widget canvas pour afficher l'image et les polygones."""
    
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.original_image = None
        self.scale = 1.0
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #2a2a2a;")
    
    def set_image(self, img):
        """Définit l'image à afficher."""
        self.original_image = img
        self.refresh()
    
    def refresh(self):
        """Rafraîchit l'affichage avec les overlays."""
        if self.original_image is None:
            return
        
        img = self.original_image.copy()
        data = self.editor.data
        
        if CONFIG.get("show_overlay"):
            # Palette de couleurs distinctes (BGR)
            COLORS = [
                (255, 100, 100), (100, 255, 100), (100, 100, 255),
                (255, 255, 100), (255, 100, 255), (100, 255, 255),
                (255, 180, 100), (180, 100, 255),
            ]
            
            opacity = CONFIG.get("overlay_opacity") or 0.4
            overlay = img.copy()
            
            for a_idx, ayat in enumerate(data.get("ayats", [])):
                color = COLORS[a_idx % len(COLORS)]
                
                for r_idx, rect in enumerate(ayat.get("rects", [])):
                    coords = rect.get("coords", [0, 0, 100, 50])
                    x, y, w, h = coords
                    
                    # Dessiner le rectangle
                    cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1)
                    
                    # Bordure si sélectionné
                    is_selected = (a_idx, r_idx) in self.editor.selected_polygons
                    is_focused = (a_idx == self.editor.focus_ayat and r_idx == self.editor.focus_rect)
                    
                    if is_focused:
                        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 3)
                    elif is_selected:
                        cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 0), 2)
            
            cv2.addWeighted(overlay, opacity, img, 1 - opacity, 0, img)
        
        # Convertir et afficher
        self._display_image(img)
    
    def _display_image(self, img):
        """Affiche l'image redimensionnée."""
        h, w = img.shape[:2]
        
        # Calculer l'échelle pour s'adapter au widget
        widget_w = self.width()
        widget_h = self.height()
        
        if widget_w > 0 and widget_h > 0:
            scale_w = widget_w / w
            scale_h = widget_h / h
            self.scale = min(scale_w, scale_h, 1.0)  # Ne pas agrandir
            
            new_w = int(w * self.scale)
            new_h = int(h * self.scale)
            
            if new_w > 0 and new_h > 0:
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
        # Convertir BGR -> RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = img_rgb.shape
        
        qimg = QImage(img_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.setPixmap(QPixmap.fromImage(qimg))
    
    def resizeEvent(self, event):
        """Recalcule l'affichage lors du redimensionnement."""
        super().resizeEvent(event)
        if self.original_image is not None:
            self.refresh()
    
    def mousePressEvent(self, event):
        """Gère les clics sur le canvas."""
        if self.original_image is None:
            return
        
        # Calculer les coordonnées dans l'image originale
        pos = event.position()
        
        # Offset du pixmap dans le label
        pixmap = self.pixmap()
        if pixmap is None:
            return
        
        label_w = self.width()
        label_h = self.height()
        pix_w = pixmap.width()
        pix_h = pixmap.height()
        
        offset_x = (label_w - pix_w) // 2
        offset_y = (label_h - pix_h) // 2
        
        img_x = int((pos.x() - offset_x) / self.scale)
        img_y = int((pos.y() - offset_y) / self.scale)
        
        # Trouver le polygon cliqué
        multi = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        
        for a_idx, ayat in enumerate(self.editor.data.get("ayats", [])):
            for r_idx, rect in enumerate(ayat.get("rects", [])):
                coords = rect.get("coords", [0, 0, 100, 50])
                x, y, w, h = coords
                
                if x <= img_x <= x + w and y <= img_y <= y + h:
                    poly = (a_idx, r_idx)
                    
                    if multi:
                        if poly in self.editor.selected_polygons:
                            self.editor.selected_polygons.remove(poly)
                        else:
                            self.editor.selected_polygons.append(poly)
                    else:
                        self.editor.selected_polygons = [poly]
                    
                    self.editor.focus_ayat = a_idx
                    self.editor.focus_rect = r_idx
                    self.editor.on_selection_changed()
                    return
        
        # Clic sur vide - désélectionner
        if not multi:
            self.editor.selected_polygons = []
            self.editor.on_selection_changed()


# =============================================================================
# FENÊTRE PRINCIPALE - ÉDITEUR RESPONSIVE
# =============================================================================
class QuranEditor(QMainWindow):
    """Fenêtre principale de l'éditeur responsive."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quran Ayat Editor - Responsive")
        self.setMinimumSize(1000, 700)
        
        # État
        self.image_files = []
        self.current_index = -1
        self.current_image = None
        self.data = {"ayats": []}
        self.has_unsaved_changes = False
        
        # Sélection
        self.selected_polygons = []
        self.focus_ayat = -1
        self.focus_rect = -1
        
        # Charger les bases
        load_surah_database()
        load_sommaire()
        
        # Interface
        self._setup_menu_bar()
        self._setup_ui()
        self._setup_shortcuts()
        self._restore_window_state()
    
    # =========================================================================
    # MENU BAR
    # =========================================================================
    def _setup_menu_bar(self):
        """Configure la barre de menus."""
        menubar = self.menuBar()
        
        # === Menu Fichier ===
        file_menu = menubar.addMenu("Fichier")
        
        open_image_action = QAction("Ouvrir image...", self)
        open_image_action.setShortcut(QKeySequence("Ctrl+O"))
        open_image_action.triggered.connect(self.open_image)
        file_menu.addAction(open_image_action)
        
        open_folder_action = QAction("Ouvrir dossier...", self)
        open_folder_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_folder_action.triggered.connect(self.open_folder)
        file_menu.addAction(open_folder_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("Sauvegarder", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self.save_json)
        file_menu.addAction(save_action)
        
        export_action = QAction("Exporter...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self.export_data)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        settings_action = QAction("Paramètres...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("Quitter", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # === Menu Edition ===
        edit_menu = menubar.addMenu("Edition")
        
        add_ayat_action = QAction("Ajouter ayat", self)
        add_ayat_action.setShortcut(QKeySequence("Ctrl+N"))
        add_ayat_action.triggered.connect(self.add_ayat)
        edit_menu.addAction(add_ayat_action)
        
        delete_ayat_action = QAction("Supprimer ayat", self)
        delete_ayat_action.setShortcut(QKeySequence("Delete"))
        delete_ayat_action.triggered.connect(self.delete_ayat)
        edit_menu.addAction(delete_ayat_action)
        
        edit_menu.addSeparator()
        
        detect_action = QAction("Auto-détecter", self)
        detect_action.setShortcut(QKeySequence("Ctrl+D"))
        detect_action.triggered.connect(self.auto_detect)
        edit_menu.addAction(detect_action)
        
        # === Menu Affichage ===
        view_menu = menubar.addMenu("Affichage")
        
        self.overlay_action = QAction("Afficher overlays", self, checkable=True)
        self.overlay_action.setChecked(CONFIG.get("show_overlay"))
        self.overlay_action.triggered.connect(self.toggle_overlay)
        view_menu.addAction(self.overlay_action)
        
        view_menu.addSeparator()
        
        zoom_in_action = QAction("Zoom +", self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl++"))
        view_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("Zoom -", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        view_menu.addAction(zoom_out_action)
        
        zoom_fit_action = QAction("Ajuster à la fenêtre", self)
        zoom_fit_action.setShortcut(QKeySequence("Ctrl+0"))
        view_menu.addAction(zoom_fit_action)
        
        # === Menu À propos ===
        help_menu = menubar.addMenu("À propos")
        
        about_action = QAction("À propos de l'application", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        help_action = QAction("Aide", self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)
    
    # =========================================================================
    # INTERFACE PRINCIPALE
    # =========================================================================
    def _setup_ui(self):
        """Configure l'interface principale responsive."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # Splitter principal horizontal
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # === PANNEAU GAUCHE ===
        left_panel = QWidget()
        left_panel.setMinimumWidth(200)
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(8)
        
        # Fichiers
        file_group = QGroupBox("Fichiers")
        file_layout = QVBoxLayout(file_group)
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self._on_file_selected)
        self.file_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        file_layout.addWidget(self.file_list)
        left_layout.addWidget(file_group, stretch=2)
        
        # Navigation
        nav_group = QGroupBox("Navigation")
        nav_layout = QHBoxLayout(nav_group)
        self.prev_btn = QPushButton("◀ Préc")
        self.prev_btn.clicked.connect(lambda: self._nav_page(-1))
        nav_layout.addWidget(self.prev_btn)
        
        self.page_spin = QSpinBox()
        self.page_spin.setRange(0, 0)
        self.page_spin.valueChanged.connect(self._go_to_page)
        nav_layout.addWidget(self.page_spin)
        
        self.page_label = QLabel("/ 0")
        nav_layout.addWidget(self.page_label)
        
        self.next_btn = QPushButton("Suiv ▶")
        self.next_btn.clicked.connect(lambda: self._nav_page(1))
        nav_layout.addWidget(self.next_btn)
        left_layout.addWidget(nav_group)
        
        # Détection
        detect_group = QGroupBox("Détection")
        detect_layout = QVBoxLayout(detect_group)
        self.detect_btn = QPushButton("🔍 Auto-détecter")
        self.detect_btn.clicked.connect(self.auto_detect)
        detect_layout.addWidget(self.detect_btn)
        left_layout.addWidget(detect_group)
        
        self.main_splitter.addWidget(left_panel)
        
        # === PANNEAU CENTRAL - CANVAS ===
        self.canvas = CanvasWidget(self)
        canvas_scroll = QScrollArea()
        canvas_scroll.setWidgetResizable(True)
        canvas_scroll.setWidget(self.canvas)
        canvas_scroll.setMinimumWidth(400)
        self.main_splitter.addWidget(canvas_scroll)
        
        # === PANNEAU DROIT ===
        right_panel = QWidget()
        right_panel.setMinimumWidth(250)
        right_panel.setMaximumWidth(450)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(8)
        
        # Liste des ayats
        ayat_group = QGroupBox("Ayats")
        ayat_layout = QVBoxLayout(ayat_group)
        self.ayat_tree = QTreeWidget()
        self.ayat_tree.setHeaderLabels(["#", "Sourate", "Ayah"])
        self.ayat_tree.setColumnWidth(0, 30)
        self.ayat_tree.setColumnWidth(1, 80)
        self.ayat_tree.itemClicked.connect(self._on_ayat_selected)
        ayat_layout.addWidget(self.ayat_tree)
        right_layout.addWidget(ayat_group, stretch=2)
        
        # Propriétés
        prop_group = QGroupBox("Propriétés")
        prop_layout = QFormLayout(prop_group)
        
        self.surah_spin = QSpinBox()
        self.surah_spin.setRange(1, 114)
        self.surah_spin.valueChanged.connect(self._on_prop_changed)
        prop_layout.addRow("Sourate:", self.surah_spin)
        
        self.surah_name_label = QLabel("Al-Fatiha")
        prop_layout.addRow("", self.surah_name_label)
        
        self.ayah_spin = QSpinBox()
        self.ayah_spin.setRange(0, 300)
        self.ayah_spin.valueChanged.connect(self._on_prop_changed)
        prop_layout.addRow("Ayah:", self.ayah_spin)
        
        right_layout.addWidget(prop_group)
        
        # Métadonnées page
        meta_group = QGroupBox("Métadonnées Page")
        meta_layout = QFormLayout(meta_group)
        
        self.juz_spin = QSpinBox()
        self.juz_spin.setRange(1, 30)
        self.juz_spin.valueChanged.connect(self._mark_changed)
        meta_layout.addRow("Juz:", self.juz_spin)
        
        self.hizb_spin = QSpinBox()
        self.hizb_spin.setRange(1, 60)
        self.hizb_spin.valueChanged.connect(self._mark_changed)
        meta_layout.addRow("Hizb:", self.hizb_spin)
        
        self.division_combo = QComboBox()
        self.division_combo.addItems(CONFIG.get_divisions())
        self.division_combo.currentIndexChanged.connect(self._mark_changed)
        meta_layout.addRow("Division:", self.division_combo)
        
        right_layout.addWidget(meta_group)
        
        # Actions
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout(action_group)
        
        btn_row1 = QHBoxLayout()
        self.add_btn = QPushButton("➕ Ajouter")
        self.add_btn.clicked.connect(self.add_ayat)
        btn_row1.addWidget(self.add_btn)
        
        self.delete_btn = QPushButton("🗑️ Supprimer")
        self.delete_btn.clicked.connect(self.delete_ayat)
        btn_row1.addWidget(self.delete_btn)
        action_layout.addLayout(btn_row1)
        
        self.save_btn = QPushButton("💾 Sauvegarder (Ctrl+S)")
        self.save_btn.clicked.connect(self.save_json)
        action_layout.addWidget(self.save_btn)
        
        right_layout.addWidget(action_group)
        
        right_layout.addStretch()
        self.main_splitter.addWidget(right_panel)
        
        # Proportions initiales
        self.main_splitter.setSizes([250, 600, 300])
        
        # Barre de statut
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Prêt - Ouvrez une image ou un dossier")
    
    def _setup_shortcuts(self):
        """Configure les raccourcis clavier."""
        QShortcut(QKeySequence("PgUp"), self, lambda: self._nav_page(-1))
        QShortcut(QKeySequence("PgDown"), self, lambda: self._nav_page(1))
        QShortcut(QKeySequence("Home"), self, lambda: self._go_to_page(0))
        QShortcut(QKeySequence("End"), self, lambda: self._go_to_page(len(self.image_files) - 1))
    
    def _restore_window_state(self):
        """Restaure l'état de la fenêtre."""
        geometry = CONFIG.get("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        splitter_state = CONFIG.get("splitter_state")
        if splitter_state:
            self.main_splitter.restoreState(splitter_state)
    
    def closeEvent(self, event):
        """Sauvegarde l'état avant fermeture."""
        if self.has_unsaved_changes:
            if not self._check_unsaved_changes():
                event.ignore()
                return
        
        CONFIG.set("window_geometry", self.saveGeometry())
        CONFIG.set("splitter_state", self.main_splitter.saveState())
        event.accept()
    
    # =========================================================================
    # CHARGEMENT FICHIERS
    # =========================================================================
    def open_image(self):
        """Ouvre une image unique."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff)"
        )
        if path:
            self.image_files = [path]
            self._refresh_file_list()
            self.load_page(0)
    
    def open_folder(self):
        """Ouvre un dossier d'images."""
        folder = QFileDialog.getExistingDirectory(self, "Ouvrir dossier images")
        if folder:
            CONFIG.set("image_dir", folder)
            self._load_folder(folder)
    
    def _load_folder(self, folder):
        """Charge les images d'un dossier."""
        extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff')
        files = []
        
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(extensions):
                files.append(os.path.join(folder, f))
        
        if not files:
            QMessageBox.warning(self, "Attention", "Aucune image trouvée dans ce dossier.")
            return
        
        self.image_files = files
        self._refresh_file_list()
        
        if self.image_files:
            self.load_page(0)
    
    def _refresh_file_list(self):
        """Actualise la liste des fichiers."""
        self.file_list.clear()
        
        for i, path in enumerate(self.image_files):
            name = os.path.basename(path)
            item = QListWidgetItem(f"{i+1}. {name}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.file_list.addItem(item)
        
        self.page_spin.setRange(1, max(1, len(self.image_files)))
        self.page_label.setText(f"/ {len(self.image_files)}")
    
    def _on_file_selected(self, item):
        """Gère la sélection d'un fichier dans la liste."""
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx != self.current_index:
            if self.has_unsaved_changes:
                if not self._check_unsaved_changes():
                    return
            self.load_page(idx)
    
    # =========================================================================
    # CHARGEMENT PAGE
    # =========================================================================
    def load_page(self, index):
        """Charge une page spécifique."""
        if index < 0 or index >= len(self.image_files):
            return
        
        # Vérifier JSON précédent
        if index > 0:
            prev_json = self._get_json_path(self.image_files[index - 1])
            if not os.path.exists(prev_json):
                meta = estimate_metadata_for_page(index)
                reply = QMessageBox.question(
                    self, "Page précédente non annotée",
                    f"La page précédente n'a pas de fichier JSON.\n"
                    f"Estimation: Juz {meta['juz']}, Hizb {meta['hizb']}, {meta['division']}\n\n"
                    "Continuer quand même?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
        
        self.current_index = index
        image_path = self.image_files[index]
        
        # Charger l'image
        self.current_image = cv2.imread(image_path)
        if self.current_image is None:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger: {image_path}")
            return
        
        # Charger les données JSON
        json_path = self._get_json_path(image_path)
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        else:
            # Initialiser avec estimation
            meta = estimate_metadata_for_page(index + 1)
            self.data = {
                "image": os.path.basename(image_path),
                "juz": meta["juz"],
                "hizb": meta["hizb"],
                "division": meta["division"],
                "ayats": []
            }
        
        # Mettre à jour l'interface
        self.canvas.set_image(self.current_image)
        self._update_ui_from_data()
        
        # Sélection dans la liste
        self.file_list.setCurrentRow(index)
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(index + 1)
        self.page_spin.blockSignals(False)
        
        self.has_unsaved_changes = False
        self.status_bar.showMessage(f"Page {index + 1}/{len(self.image_files)} - {os.path.basename(image_path)}")
    
    def _get_json_path(self, image_path):
        """Retourne le chemin du fichier JSON correspondant."""
        json_dir = CONFIG.get("json_dir")
        if not json_dir:
            json_dir = os.path.dirname(image_path)
        
        base = os.path.splitext(os.path.basename(image_path))[0]
        return os.path.join(json_dir, f"{base}.json")
    
    def _update_ui_from_data(self):
        """Met à jour l'interface depuis les données."""
        # Métadonnées
        self.juz_spin.blockSignals(True)
        self.hizb_spin.blockSignals(True)
        self.division_combo.blockSignals(True)
        
        self.juz_spin.setValue(self.data.get("juz", 1))
        self.hizb_spin.setValue(self.data.get("hizb", 1))
        
        division = self.data.get("division", "start")
        divisions = CONFIG.get_divisions()
        if division in divisions:
            self.division_combo.setCurrentIndex(divisions.index(division))
        
        self.juz_spin.blockSignals(False)
        self.hizb_spin.blockSignals(False)
        self.division_combo.blockSignals(False)
        
        # Liste des ayats
        self._refresh_ayat_tree()
    
    def _refresh_ayat_tree(self):
        """Actualise l'arbre des ayats."""
        self.ayat_tree.clear()
        
        for i, ayat in enumerate(self.data.get("ayats", [])):
            surah = ayat.get("surah", 1)
            ayah = ayat.get("ayah", 0)
            surah_name = SURAH_DB.get(surah, "?")
            
            item = QTreeWidgetItem([str(i + 1), surah_name, str(ayah)])
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            self.ayat_tree.addTopLevelItem(item)
    
    # =========================================================================
    # NAVIGATION
    # =========================================================================
    def _nav_page(self, delta):
        """Navigue vers la page suivante/précédente."""
        if self.has_unsaved_changes:
            if not self._check_unsaved_changes():
                return
        
        new_idx = self.current_index + delta
        if 0 <= new_idx < len(self.image_files):
            self.load_page(new_idx)
    
    def _go_to_page(self, page_num):
        """Va à une page spécifique (1-indexed depuis le spinbox)."""
        idx = page_num - 1
        if idx != self.current_index and 0 <= idx < len(self.image_files):
            if self.has_unsaved_changes:
                if not self._check_unsaved_changes():
                    self.page_spin.blockSignals(True)
                    self.page_spin.setValue(self.current_index + 1)
                    self.page_spin.blockSignals(False)
                    return
            self.load_page(idx)
    
    def _check_unsaved_changes(self):
        """Vérifie les modifications non sauvegardées."""
        reply = QMessageBox.question(
            self, "Modifications non sauvegardées",
            "Vous avez des modifications non sauvegardées.\n\nVoulez-vous les sauvegarder?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        
        if reply == QMessageBox.StandardButton.Save:
            self.save_json()
            return True
        elif reply == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False
    
    # =========================================================================
    # SÉLECTION & PROPRIÉTÉS
    # =========================================================================
    def _on_ayat_selected(self, item):
        """Gère la sélection d'un ayat dans l'arbre."""
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        self.focus_ayat = idx
        self.focus_rect = 0 if self.data["ayats"][idx].get("rects") else -1
        self.selected_polygons = [(idx, 0)] if self.focus_rect >= 0 else []
        self.on_selection_changed()
    
    def on_selection_changed(self):
        """Met à jour l'interface lors d'un changement de sélection."""
        self.canvas.refresh()
        
        if self.focus_ayat >= 0 and self.focus_ayat < len(self.data.get("ayats", [])):
            ayat = self.data["ayats"][self.focus_ayat]
            
            self.surah_spin.blockSignals(True)
            self.ayah_spin.blockSignals(True)
            
            self.surah_spin.setValue(ayat.get("surah", 1))
            self.ayah_spin.setValue(ayat.get("ayah", 0))
            
            self.surah_spin.blockSignals(False)
            self.ayah_spin.blockSignals(False)
            
            self.surah_name_label.setText(SURAH_DB.get(ayat.get("surah", 1), "?"))
    
    def _on_prop_changed(self):
        """Gère les changements de propriétés."""
        if self.focus_ayat < 0 or self.focus_ayat >= len(self.data.get("ayats", [])):
            return
        
        self.data["ayats"][self.focus_ayat]["surah"] = self.surah_spin.value()
        self.data["ayats"][self.focus_ayat]["ayah"] = self.ayah_spin.value()
        
        self.surah_name_label.setText(SURAH_DB.get(self.surah_spin.value(), "?"))
        self._refresh_ayat_tree()
        self._mark_changed()
    
    def _mark_changed(self):
        """Marque les données comme modifiées."""
        self.has_unsaved_changes = True
        self.status_bar.showMessage("⚠️ Modifications non sauvegardées")
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    def add_ayat(self):
        """Ajoute un nouvel ayat."""
        if self.current_image is None:
            return
        
        h, w = self.current_image.shape[:2]
        
        # Déterminer sourate et ayah
        last_surah = 1
        last_ayah = 0
        
        if self.data.get("ayats"):
            last = self.data["ayats"][-1]
            last_surah = last.get("surah", 1)
            last_ayah = last.get("ayah", 0)
        
        new_ayat = {
            "surah": last_surah,
            "ayah": last_ayah + 1,
            "rects": [{
                "coords": [w // 4, len(self.data["ayats"]) * 60 + 50, w // 2, 50]
            }]
        }
        
        self.data["ayats"].append(new_ayat)
        self._refresh_ayat_tree()
        self.canvas.refresh()
        self._mark_changed()
    
    def delete_ayat(self):
        """Supprime l'ayat sélectionné."""
        if self.focus_ayat < 0 or self.focus_ayat >= len(self.data.get("ayats", [])):
            return
        
        reply = QMessageBox.question(
            self, "Confirmer suppression",
            f"Supprimer l'ayat #{self.focus_ayat + 1}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.data["ayats"][self.focus_ayat]
            self.focus_ayat = -1
            self.focus_rect = -1
            self.selected_polygons = []
            self._refresh_ayat_tree()
            self.canvas.refresh()
            self._mark_changed()
    
    def save_json(self):
        """Sauvegarde les données JSON."""
        if self.current_index < 0:
            return
        
        # Mettre à jour les métadonnées
        self.data["juz"] = self.juz_spin.value()
        self.data["hizb"] = self.hizb_spin.value()
        self.data["division"] = self.division_combo.currentText()
        
        json_path = self._get_json_path(self.image_files[self.current_index])
        
        # Créer le dossier si nécessaire
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        
        self.has_unsaved_changes = False
        self.status_bar.showMessage(f"✅ Sauvegardé: {os.path.basename(json_path)}")
    
    def export_data(self):
        """Exporte les données."""
        QMessageBox.information(self, "Export", "Fonctionnalité d'export à implémenter.")
    
    # =========================================================================
    # DÉTECTION AUTOMATIQUE
    # =========================================================================
    def auto_detect(self):
        """Lance la détection automatique des ayats."""
        if self.current_image is None:
            QMessageBox.warning(self, "Attention", "Aucune image chargée.")
            return
        
        # Vérifier les échantillons
        sample_ayat = CONFIG.get("sample_ayat_mark")
        if not sample_ayat or not os.path.exists(sample_ayat):
            QMessageBox.warning(
                self, "Attention",
                "Échantillon de marque ayat non configuré.\n"
                "Allez dans Fichier > Paramètres > Échantillons."
            )
            return
        
        self.status_bar.showMessage("🔍 Détection en cours...")
        QApplication.processEvents()
        
        try:
            detected = self._detect_ayat_marks(sample_ayat)
            
            if detected:
                self.data["ayats"] = detected
                self._refresh_ayat_tree()
                self.canvas.refresh()
                self._mark_changed()
                self.status_bar.showMessage(f"✅ {len(detected)} ayat(s) détecté(s)")
            else:
                self.status_bar.showMessage("⚠️ Aucun ayat détecté")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur de détection: {e}")
            self.status_bar.showMessage("❌ Erreur de détection")
    
    def _detect_ayat_marks(self, sample_path):
        """Détecte les marques d'ayat dans l'image."""
        template = cv2.imread(sample_path)
        if template is None:
            return []
        
        img_gray = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        
        # Multi-scale template matching
        detected = []
        best_scale = 1.0
        
        for scale in np.linspace(0.5, 1.5, 11):
            w = int(tpl_gray.shape[1] * scale)
            h = int(tpl_gray.shape[0] * scale)
            if w < 10 or h < 10:
                continue
            
            resized = cv2.resize(tpl_gray, (w, h))
            result = cv2.matchTemplate(img_gray, resized, cv2.TM_CCOEFF_NORMED)
            
            threshold = 0.7
            locations = np.where(result >= threshold)
            
            for pt in zip(*locations[::-1]):
                detected.append({
                    "x": pt[0], "y": pt[1],
                    "w": w, "h": h,
                    "score": result[pt[1], pt[0]]
                })
        
        # Non-maximum suppression
        detected = sorted(detected, key=lambda x: x["score"], reverse=True)
        final = []
        
        for d in detected:
            overlap = False
            for f in final:
                if abs(d["x"] - f["x"]) < 30 and abs(d["y"] - f["y"]) < 30:
                    overlap = True
                    break
            if not overlap:
                final.append(d)
        
        # Trier par position Y puis X
        final = sorted(final, key=lambda x: (x["y"], x["x"]))
        
        # Convertir en format ayat
        ayats = []
        for i, d in enumerate(final):
            ayats.append({
                "surah": get_surah_for_page(self.current_index + 1),
                "ayah": i + 1,
                "rects": [{
                    "coords": [d["x"], d["y"], d["w"], d["h"]]
                }]
            })
        
        return ayats
    
    # =========================================================================
    # MENUS ACTIONS
    # =========================================================================
    def show_settings(self):
        """Affiche le dialogue des paramètres."""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Recharger le sommaire si changé
            load_sommaire()
            # Mettre à jour les divisions
            self.division_combo.clear()
            self.division_combo.addItems(CONFIG.get_divisions())
            self.canvas.refresh()
    
    def show_about(self):
        """Affiche le dialogue À propos."""
        AboutDialog(self).exec()
    
    def show_help(self):
        """Affiche l'aide."""
        QMessageBox.information(
            self, "Aide",
            "Quran Ayat Editor - Aide\n\n"
            "Raccourcis clavier:\n"
            "- Ctrl+O: Ouvrir image\n"
            "- Ctrl+Shift+O: Ouvrir dossier\n"
            "- Ctrl+S: Sauvegarder\n"
            "- Ctrl+D: Auto-détecter\n"
            "- Ctrl+N: Ajouter ayat\n"
            "- Delete: Supprimer ayat\n"
            "- PgUp/PgDown: Navigation\n\n"
            "Utilisez les paramètres pour configurer\n"
            "les échantillons et les options de détection."
        )
    
    def toggle_overlay(self):
        """Bascule l'affichage des overlays."""
        CONFIG.set("show_overlay", self.overlay_action.isChecked())
        self.canvas.refresh()


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================
def main():
    """Point d'entrée de l'application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Quran Ayat Editor")
    app.setOrganizationName("QuranEditor")
    
    # Style
    if CONFIG.get("theme") == "dark":
        app.setStyle("Fusion")
        palette = app.palette()
        from PyQt6.QtGui import QColor, QPalette
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        app.setPalette(palette)
    
    # Charger le dossier depuis les paramètres
    window = QuranEditor()
    
    image_dir = CONFIG.get("image_dir")
    if image_dir and os.path.isdir(image_dir):
        window._load_folder(image_dir)
    
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
