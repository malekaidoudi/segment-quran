#!/usr/bin/env python3
"""
Quran Audio Splitter - Module de segmentation audio
====================================================

Application PyQt6 pour la segmentation automatique de fichiers audio 
de récitation coranique. Permet de découper un fichier MP3 en segments 
individuels basés sur les pauses du récitateur.

Fonctionnalités principales:
- Détection automatique des silences pour segmentation
- Mode Sourate et mode Juz (multi-sourate)
- Fusion et division de segments
- Prévisualisation des ayats avec images
- Historique d'annulation pour les opérations

Auteur: [Votre nom]
Version: 2.0
"""

import sys
import os
import glob
import shutil
import time
import tempfile
import subprocess
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QSpinBox, QProgressBar,
    QFileDialog, QListWidget, QGroupBox, QMessageBox, QSplitter,
    QListWidgetItem, QDialog, QDoubleSpinBox, QCheckBox, QScrollArea,
    QStyledItemDelegate, QStyle, QInputDialog, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer, QTime, QRect, QPoint, QEvent
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPolygon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

try:
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

import data_manager

# Hugging Face integration
try:
    from huggingface_hub import HfApi, list_repo_files, upload_folder
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

# =============================================================================
# CONFIGURATION
# =============================================================================
class Config:
    """
    Configuration globale du module audio.
    
    Contient tous les chemins, paramètres par défaut et constantes
    utilisés dans l'application.
    """
    _BASE = str(data_manager.DATA_DIR)
    AUDIO_INPUT_DIR = os.path.join(_BASE, "audio", "input")
    AUDIO_OUTPUT_DIR = os.path.join(_BASE, "audio", "output")
    AYATS_CSV = os.path.join(_BASE, "ayats.csv")
    ANNOTATIONS_DIR = os.path.join(_BASE, "annotations")
    IMAGES_DIR = os.path.join(_BASE, "images")
    AYAT_CACHE_DIR = os.path.join(_BASE, "audio", "ayat_cache")
    
    # Paramètres par défaut de détection de silence
    DEFAULT_SILENCE_THRESH = -40      # dB
    DEFAULT_MIN_SILENCE_LEN = 500     # ms
    DEFAULT_KEEP_SILENCE = 200        # ms
    
    # Limites des paramètres
    SILENCE_THRESH_MIN = -60
    SILENCE_THRESH_MAX = -20
    MIN_SILENCE_LEN_MIN = 100
    MIN_SILENCE_LEN_MAX = 2000
    KEEP_SILENCE_MIN = 0
    KEEP_SILENCE_MAX = 500
    
    # Nombre total d'ayats par sourate
    SURAH_AYAT_COUNT = {
        1: 7, 2: 286, 3: 200, 4: 176, 5: 120, 6: 165, 7: 206, 8: 75,
        9: 129, 10: 109, 11: 123, 12: 111, 13: 43, 14: 52, 15: 99,
        16: 128, 17: 111, 18: 110, 19: 98, 20: 135, 21: 112, 22: 78,
        23: 118, 24: 64, 25: 77, 26: 227, 27: 93, 28: 88, 29: 69,
        30: 60, 31: 34, 32: 30, 33: 73, 34: 54, 35: 45, 36: 83,
        37: 182, 38: 88, 39: 75, 40: 85, 41: 54, 42: 53, 43: 89,
        44: 59, 45: 37, 46: 35, 47: 38, 48: 29, 49: 18, 50: 45,
        51: 60, 52: 49, 53: 62, 54: 55, 55: 78, 56: 96, 57: 29,
        58: 22, 59: 24, 60: 13, 61: 14, 62: 11, 63: 11, 64: 18,
        65: 12, 66: 12, 67: 30, 68: 52, 69: 52, 70: 44, 71: 28,
        72: 28, 73: 20, 74: 56, 75: 40, 76: 31, 77: 50, 78: 40,
        79: 46, 80: 42, 81: 29, 82: 19, 83: 36, 84: 25, 85: 22,
        86: 17, 87: 19, 88: 26, 89: 30, 90: 20, 91: 15, 92: 21,
        93: 11, 94: 8, 95: 8, 96: 19, 97: 5, 98: 8, 99: 8, 100: 11,
        101: 11, 102: 8, 103: 3, 104: 9, 105: 5, 106: 4, 107: 7,
        108: 3, 109: 6, 110: 3, 111: 5, 112: 4, 113: 5, 114: 6
    }
    
    # Fichier de log des actions
    ACTION_LOG_FILE = os.path.join(_BASE, "audio", "action_log.txt")
    
    # Fichier de session (pour reprendre le travail)
    SESSION_FILE = os.path.join(_BASE, "audio", "session.json")


# =============================================================================
# HUGGING FACE SYNC UTILITIES
# =============================================================================

def _get_hf_token() -> Optional[str]:
    """Récupère le token HF depuis les variables d'environnement."""
    return os.getenv("HUGGINGFACE_TOKEN")


def _get_hf_repo() -> str:
    """Récupère le repo HF depuis les variables d'environnement."""
    return os.getenv("HF_DATASET_REPO", "malekaidoudi/segment-quran-data")


def get_remote_completed_surahs() -> set:
    """
    Vérifie sur Hugging Face quelles sourates ont déjà été uploadées.
    Retourne un set de numéros de sourates (int) déjà présentes sur HF.
    """
    if not HF_AVAILABLE:
        return set()
    
    token = _get_hf_token()
    if not token:
        return set()
    
    try:
        api = HfApi(token=token)
        repo_id = _get_hf_repo()
        
        # Lister les fichiers dans le dataset
        files = list_repo_files(repo_id=repo_id, repo_type="dataset", token=token)
        
        completed = set()
        for f in files:
            # Chercher les dossiers audio/output/XXX/ ou audio/output/juz_XX_temp/
            if "audio/output/" in f:
                parts = f.split("/")
                try:
                    idx = parts.index("output")
                    folder = parts[idx + 1] if idx + 1 < len(parts) else ""
                    # Sourate numérique: 001-114
                    if folder.isdigit() and 1 <= int(folder) <= 114:
                        completed.add(int(folder))
                except (ValueError, IndexError):
                    pass
        
        return completed
    except Exception as e:
        print(f"⚠️ Erreur vérification HF: {e}")
        return set()


def get_local_completed_surahs() -> set:
    """
    Vérifie localement quelles sourates ont déjà été segmentées.
    Retourne un set de numéros de sourates (int) avec des fichiers MP3.
    """
    completed = set()
    output_dir = Config.AUDIO_OUTPUT_DIR
    
    if not os.path.exists(output_dir):
        return completed
    
    for entry in os.listdir(output_dir):
        entry_path = os.path.join(output_dir, entry)
        if os.path.isdir(entry_path):
            # Vérifier si c'est un dossier de sourate numérique
            if entry.isdigit():
                surah_num = int(entry)
                if 1 <= surah_num <= 114:
                    # Vérifier qu'il contient des MP3
                    mp3_files = glob.glob(os.path.join(entry_path, "*.mp3"))
                    if mp3_files:
                        completed.add(surah_num)
    
    return completed


def upload_surah_to_hf(surah_num: int, parent_widget=None) -> bool:
    """
    Upload un dossier de sourate spécifique vers Hugging Face.
    """
    if not HF_AVAILABLE:
        if parent_widget:
            QMessageBox.warning(parent_widget, "HF non disponible",
                                "huggingface_hub n'est pas installé.\npip install huggingface_hub")
        return False
    
    token = _get_hf_token()
    if not token:
        if parent_widget:
            QMessageBox.warning(parent_widget, "Token manquant",
                                "HUGGINGFACE_TOKEN non défini dans .env")
        return False
    
    surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{surah_num:03d}")
    if not os.path.exists(surah_dir):
        if parent_widget:
            QMessageBox.warning(parent_widget, "Dossier non trouvé",
                                f"Dossier local introuvable:\n{surah_dir}")
        return False
    
    try:
        api = HfApi(token=token)
        repo_id = _get_hf_repo()
        
        # Upload du dossier de la sourate
        api.upload_folder(
            folder_path=surah_dir,
            path_in_repo=f"audio/output/{surah_num:03d}",
            repo_id=repo_id,
            repo_type="dataset",
        )
        
        return True
    except Exception as e:
        if parent_widget:
            QMessageBox.critical(parent_widget, "Erreur upload", str(e))
        return False


def delete_surah_locally(surah_num: int) -> bool:
    """Supprime localement le dossier d'une sourate."""
    surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{surah_num:03d}")
    if os.path.exists(surah_dir):
        try:
            shutil.rmtree(surah_dir)
            return True
        except Exception:
            return False
    return False


# =============================================================================
# SYSTÈME DE LOG DES ACTIONS
# =============================================================================
class ActionLogger:
    """
    Logger pour tracer toutes les opérations critiques (fusion, division, etc.)
    
    Chaque entrée contient:
    - Horodatage précis
    - Type d'action
    - État avant/après
    - Fichiers concernés
    - Paramètres de l'opération
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.log_file = Config.ACTION_LOG_FILE
        self._ensure_log_dir()
        self._write_header()
    
    def _ensure_log_dir(self):
        """Crée le dossier de log si nécessaire."""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
    
    def _write_header(self):
        """Écrit l'en-tête du fichier log si nouveau."""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("AUDIO SPLITTER - LOG DES ACTIONS\n")
                f.write(f"Créé le: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
    
    def _format_timestamp(self) -> str:
        """Retourne l'horodatage formaté."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    def _log(self, action: str, details: Dict[str, Any]) -> None:
        """Écrit une entrée de log."""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'─' * 60}\n")
                f.write(f"[{self._format_timestamp()}] {action}\n")
                f.write(f"{'─' * 60}\n")
                for key, value in details.items():
                    if isinstance(value, list):
                        f.write(f"  {key}:\n")
                        for i, item in enumerate(value):
                            f.write(f"    [{i}] {item}\n")
                    elif isinstance(value, dict):
                        f.write(f"  {key}:\n")
                        for k, v in value.items():
                            f.write(f"    {k}: {v}\n")
                    else:
                        f.write(f"  {key}: {value}\n")
        except Exception as e:
            print(f"⚠️ Erreur écriture log: {e}")
    
    def log_merge_start(self, indices: List[int], file_paths: List[str], 
                        item_texts: List[str], output_dir: str, 
                        silence_duration: int) -> None:
        """Log le début d'une fusion."""
        self._log("🔗 FUSION - DÉBUT", {
            "indices_sélectionnés": indices,
            "fichiers": file_paths,
            "textes_items": item_texts,
            "dossier_sortie": output_dir,
            "silence_entre_segments_ms": silence_duration,
            "nb_segments": len(file_paths)
        })
    
    def log_merge_complete(self, merged_path: str, merged_text: str, 
                           duration_ms: int, backup_files: List[str]) -> None:
        """Log la fin d'une fusion réussie."""
        self._log("✅ FUSION - TERMINÉE", {
            "fichier_fusionné": merged_path,
            "texte_final": merged_text,
            "durée_ms": duration_ms,
            "durée_sec": f"{duration_ms/1000:.1f}s",
            "backups_créés": backup_files
        })
    
    def log_merge_error(self, error: str, state: Dict) -> None:
        """Log une erreur de fusion."""
        self._log("❌ FUSION - ERREUR", {
            "erreur": error,
            "état_au_moment_erreur": state
        })
    
    def log_split_start(self, file_path: str, item_text: str, 
                        split_point_sec: float, segment_idx: int) -> None:
        """Log le début d'une division."""
        self._log("✂️ DIVISION - DÉBUT", {
            "fichier": file_path,
            "texte_item": item_text,
            "point_coupure_sec": f"{split_point_sec:.2f}s",
            "index_segment": segment_idx
        })
    
    def log_split_complete(self, original_path: str, part1_path: str, 
                           part2_path: str, duration1_ms: int, 
                           duration2_ms: int) -> None:
        """Log la fin d'une division réussie."""
        self._log("✅ DIVISION - TERMINÉE", {
            "fichier_original": original_path,
            "partie_1": part1_path,
            "partie_2": part2_path,
            "durée_partie1_sec": f"{duration1_ms/1000:.1f}s",
            "durée_partie2_sec": f"{duration2_ms/1000:.1f}s"
        })
    
    def log_split_error(self, error: str, state: Dict) -> None:
        """Log une erreur de division."""
        self._log("❌ DIVISION - ERREUR", {
            "erreur": error,
            "état_au_moment_erreur": state
        })
    
    def log_delete(self, file_path: str, item_text: str, 
                   segment_idx: int, files_renamed: List[Tuple[str, str]]) -> None:
        """Log une suppression."""
        self._log("🗑️ SUPPRESSION", {
            "fichier_supprimé": file_path,
            "texte_item": item_text,
            "index_segment": segment_idx,
            "fichiers_renommés": [f"{old} → {new}" for old, new in files_renamed]
        })
    
    def log_insert(self, position: int, source_file: str, 
                   output_path: str, trimmed_duration_ms: int) -> None:
        """Log une insertion."""
        self._log("➕ INSERTION", {
            "position": position,
            "fichier_source": source_file,
            "fichier_créé": output_path,
            "durée_ms": trimmed_duration_ms
        })
    
    def log_undo_merge(self, backup_data: Dict) -> None:
        """Log une annulation de fusion."""
        self._log("↩️ ANNULATION FUSION", {
            "indices_originaux": backup_data.get('indices', []),
            "fichiers_restaurés": [f.get('original', '') for f in backup_data.get('files', [])],
            "textes_originaux": backup_data.get('texts', [])
        })
    
    def log_undo_split(self, backup_data: Dict) -> None:
        """Log une annulation de division."""
        self._log("↩️ ANNULATION DIVISION", {
            "fichier_original": backup_data.get('original_file', ''),
            "fichier_backup": backup_data.get('original_backup', ''),
            "nouveau_fichier_supprimé": backup_data.get('new_file', '')
        })
    
    def log_renumber(self, output_dir: str, mappings: List[Tuple[str, str]]) -> None:
        """Log un renommage de fichiers."""
        if mappings:
            self._log("🔢 RENOMMAGE FICHIERS", {
                "dossier": output_dir,
                "renommages": [f"{old} → {new}" for old, new in mappings]
            })
    
    def log_transfer(self, from_dir: str, to_dir: str, 
                     segment_count: int, surah_num: int) -> None:
        """Log un transfert de segments."""
        self._log("📤 TRANSFERT SEGMENTS", {
            "dossier_source": from_dir,
            "dossier_destination": to_dir,
            "nombre_segments": segment_count,
            "sourate": surah_num
        })
    
    def log_state_snapshot(self, context: str, segment_count: int,
                           file_list: List[str]) -> None:
        """Log un instantané de l'état actuel."""
        self._log(f"📸 ÉTAT - {context}", {
            "nombre_segments": segment_count,
            "fichiers_présents": file_list[:20],  # Limiter à 20
            "total_fichiers": len(file_list)
        })


# Instance globale du logger
action_logger = ActionLogger()


# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

def format_time_ms(ms: int) -> str:
    """
    Convertit des millisecondes en format mm:ss.
    
    Args:
        ms: Durée en millisecondes
        
    Returns:
        Chaîne formatée "m:ss" ou "mm:ss"
    """
    total_seconds = ms / 1000
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    return f"{minutes}:{seconds:02d}"


def format_time_ms_detailed(ms: int) -> str:
    """
    Convertit des millisecondes en format mm:ss.d (avec décimale).
    
    Args:
        ms: Durée en millisecondes
        
    Returns:
        Chaîne formatée "m:ss.d"
    """
    total_seconds = ms / 1000
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:04.1f}"


def get_output_dir(juz_mode: bool, juz_num: int = 0, surah_num: int = 0) -> str:
    """
    Retourne le chemin du dossier de sortie selon le mode.
    
    Args:
        juz_mode: True si mode Juz actif
        juz_num: Numéro du Juz (si mode Juz)
        surah_num: Numéro de la sourate (si mode normal)
        
    Returns:
        Chemin absolu du dossier de sortie
    """
    if juz_mode:
        return os.path.join(Config.AUDIO_OUTPUT_DIR, f"juz_{juz_num:02d}_temp")
    return os.path.join(Config.AUDIO_OUTPUT_DIR, f"{surah_num:03d}")


def get_segment_files(output_dir: str) -> List[str]:
    """
    Retourne la liste triée des fichiers MP3 dans un dossier.
    
    Args:
        output_dir: Chemin du dossier
        
    Returns:
        Liste des chemins de fichiers MP3 triés
    """
    return sorted(glob.glob(os.path.join(output_dir, "[0-9][0-9][0-9].mp3")))


def create_backup_dir(output_dir: str, prefix: str = "_backup") -> str:
    """
    Crée un dossier de backup et retourne son chemin.
    
    Args:
        output_dir: Dossier parent
        prefix: Préfixe du dossier backup
        
    Returns:
        Chemin du dossier backup créé
    """
    backup_dir = os.path.join(output_dir, prefix)
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


# =============================================================================
# DELEGATE POUR AFFICHER PROGRESS BAR DANS LA LISTE
# =============================================================================
class SegmentItemDelegate(QStyledItemDelegate):
    """
    Delegate personnalisé pour afficher des barres de progression en colonnes.
    
    Affichage en 3 colonnes:
    - Col 1 (40%): Nom du segment (toujours visible)
    - Col 2 (30%): Barre de lecture + icône play/pause (visible pendant lecture)
    - Col 3 (30%): Barre d'opération (visible pendant fusion/division)
    
    Attributes:
        playback_progress: Dict associant chaque ligne à sa progression de lecture
        operation_progress: Dict associant chaque ligne à sa progression d'opération
    """
    
    # Couleurs
    COLOR_PLAYBACK_DONE = QColor(52, 152, 219)      # Bleu - partie lue
    COLOR_PLAYBACK_REMAIN = QColor(200, 200, 200)   # Gris clair - partie restante
    COLOR_OPERATION_DONE = QColor(230, 126, 34)     # Orange - progression
    COLOR_OPERATION_REMAIN = QColor(180, 180, 180)  # Gris - restant
    COLOR_BAR_BORDER = QColor(150, 150, 150)        # Bordure
    COLOR_PLAY_ICON = QColor(52, 152, 219)          # Bleu pour icône play
    
    # Dimensions et proportions
    BAR_HEIGHT = 10
    BAR_MARGIN = 3
    COL1_RATIO = 0.40  # 40% pour le texte
    COL2_RATIO = 0.30  # 30% pour la barre de lecture
    COL3_RATIO = 0.30  # 30% pour la barre d'opération
    ICON_SIZE = 12
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.playback_progress: Dict[int, float] = {}
        self.operation_progress: Dict[int, float] = {}
    
    def _set_progress(self, progress_dict: dict, row: int, progress: float) -> None:
        """Définit une progression (0.0-1.0) pour une ligne."""
        if progress <= 0:
            progress_dict.pop(row, None)
        else:
            progress_dict[row] = min(1.0, max(0.0, progress))
    
    def set_playback_progress(self, row: int, progress: float) -> None:
        """Définit la progression de lecture pour une ligne."""
        self._set_progress(self.playback_progress, row, progress)
    
    def set_operation_progress(self, row: int, progress: float) -> None:
        """Définit la progression d'opération pour une ligne."""
        self._set_progress(self.operation_progress, row, progress)
    
    def clear_all_progress(self) -> None:
        """Efface toutes les barres de progression."""
        self.playback_progress.clear()
        self.operation_progress.clear()
    
    def _draw_play_icon(self, painter: QPainter, x: int, y: int, size: int) -> None:
        """Dessine un triangle de lecture (▶)."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self.COLOR_PLAY_ICON))
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Triangle pointant vers la droite
        triangle = QPolygon([
            QPoint(x, y),
            QPoint(x, y + size),
            QPoint(x + size, y + size // 2)
        ])
        painter.drawPolygon(triangle)
        painter.restore()
    
    def _draw_progress_bar(self, painter: QPainter, x: int, y: int, 
                           width: int, height: int, progress: float,
                           color_done: QColor, color_remain: QColor) -> None:
        """Dessine une barre de progression horizontale."""
        done_width = int(width * progress)
        
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Fond (partie restante)
        painter.fillRect(QRect(x, y, width, height), color_remain)
        
        # Progression (partie terminée)
        if done_width > 0:
            painter.fillRect(QRect(x, y, done_width, height), color_done)
        
        # Bordure
        painter.setPen(self.COLOR_BAR_BORDER)
        painter.drawRect(QRect(x, y, width - 1, height - 1))
        
        painter.restore()
    
    def paint(self, painter: QPainter, option, index) -> None:
        """Dessine l'item avec texte + barres de progression en colonnes."""
        row = index.row()
        rect = option.rect
        
        has_playback = row in self.playback_progress
        has_operation = row in self.operation_progress
        
        # Calculer les zones des colonnes
        total_width = rect.width()
        col1_width = int(total_width * self.COL1_RATIO)
        col2_width = int(total_width * self.COL2_RATIO)
        col3_width = total_width - col1_width - col2_width
        
        col1_x = rect.left()
        col2_x = col1_x + col1_width
        col3_x = col2_x + col2_width
        
        # Dessiner le fond de sélection
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, option.palette.highlight())
        
        # --- Colonne 1: Texte du segment (toujours visible) ---
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text:
            painter.save()
            text_rect = QRect(col1_x + 5, rect.top(), col1_width - 10, rect.height())
            
            # Couleur du texte selon sélection
            if option.state & QStyle.StateFlag.State_Selected:
                painter.setPen(option.palette.highlightedText().color())
            else:
                painter.setPen(option.palette.text().color())
            
            # Tronquer le texte si trop long
            metrics = painter.fontMetrics()
            elided_text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_text)
            painter.restore()
        
        # --- Colonne 2: Barre de lecture (seulement pendant lecture) ---
        if has_playback:
            bar_y = rect.top() + (rect.height() - self.BAR_HEIGHT) // 2
            icon_x = col2_x + self.BAR_MARGIN
            bar_x = icon_x + self.ICON_SIZE + 5
            bar_width = col2_width - self.ICON_SIZE - self.BAR_MARGIN * 2 - 5
            
            # Icône play
            icon_y = rect.top() + (rect.height() - self.ICON_SIZE) // 2
            self._draw_play_icon(painter, icon_x, icon_y, self.ICON_SIZE)
            
            # Barre de progression
            self._draw_progress_bar(
                painter, bar_x, bar_y, bar_width, self.BAR_HEIGHT,
                self.playback_progress[row],
                self.COLOR_PLAYBACK_DONE, self.COLOR_PLAYBACK_REMAIN
            )
        
        # --- Colonne 3: Barre d'opération (seulement pendant fusion/division) ---
        if has_operation:
            bar_y = rect.top() + (rect.height() - self.BAR_HEIGHT) // 2
            bar_x = col3_x + self.BAR_MARGIN
            bar_width = col3_width - self.BAR_MARGIN * 2
            
            self._draw_progress_bar(
                painter, bar_x, bar_y, bar_width, self.BAR_HEIGHT,
                self.operation_progress[row],
                self.COLOR_OPERATION_DONE, self.COLOR_OPERATION_REMAIN
            )


# =============================================================================
# FONCTIONS DE VÉRIFICATION
# =============================================================================
def load_quran_text():
    """Charge le texte du Quran depuis le CSV."""
    import pandas as pd
    if os.path.exists(Config.AYATS_CSV):
        df = pd.read_csv(Config.AYATS_CSV)
        return df
    return None

def get_ayat_text(df, surah: int, ayah: int) -> str:
    """Récupère le texte d'un ayat spécifique."""
    if df is None:
        return ""
    row = df[(df['surah'] == surah) & (df['ayah'] == ayah)]
    if not row.empty:
        return row.iloc[0]['text']
    return ""

def estimate_duration_from_text(text: str) -> float:
    """Estime la durée audio basée sur la longueur du texte.
    
    Règle approximative: ~0.15 seconde par caractère arabe pour une récitation moyenne.
    """
    # Enlever les diacritiques pour compter les lettres principales
    import re
    # Caractères arabes de base (sans diacritiques)
    base_chars = len(re.sub(r'[\u064B-\u065F\u0670]', '', text))
    # Estimation: 0.12 à 0.18 sec par caractère
    return base_chars * 0.15

def verify_segments(surah_num: int, start_ayah: int, segments_info: list, quran_df) -> dict:
    """Vérifie les segments audio contre le texte du Quran.
    
    Args:
        surah_num: Numéro de la sourate
        start_ayah: Ayah de départ
        segments_info: Liste de tuples (duration_ms, file_path)
        quran_df: DataFrame du texte coranique
    
    Returns:
        dict avec les résultats de vérification
    """
    results = {
        'total_segments': len(segments_info),
        'expected_ayats': Config.SURAH_AYAT_COUNT.get(surah_num, 0) - start_ayah + 1,
        'count_match': False,
        'anomalies': [],
        'details': []
    }
    
    # 1. Vérification du comptage
    expected = results['expected_ayats']
    actual = results['total_segments']
    results['count_match'] = (actual == expected)
    
    if actual != expected:
        diff = actual - expected
        if diff > 0:
            results['anomalies'].append(f"⚠️ {diff} segment(s) en trop - ayat(s) probablement coupé(s)")
        else:
            results['anomalies'].append(f"⚠️ {-diff} segment(s) manquant(s) - ayat(s) probablement fusionné(s)")
    
    # 2. Vérification des durées
    if quran_df is not None:
        for i, (duration_ms, file_path) in enumerate(segments_info):
            ayah_num = start_ayah + i
            text = get_ayat_text(quran_df, surah_num, ayah_num)
            
            if text:
                expected_duration = estimate_duration_from_text(text)
                actual_duration = duration_ms / 1000
                
                # Tolérance de 50%
                ratio = actual_duration / expected_duration if expected_duration > 0 else 1
                
                detail = {
                    'ayah': ayah_num,
                    'text_preview': text[:50] + "..." if len(text) > 50 else text,
                    'text_length': len(text),
                    'expected_sec': round(expected_duration, 1),
                    'actual_sec': round(actual_duration, 1),
                    'ratio': round(ratio, 2),
                    'status': 'ok'
                }
                
                if ratio < 0.4:
                    detail['status'] = 'too_short'
                    results['anomalies'].append(
                        f"🔴 A{ayah_num}: Trop court ({actual_duration:.1f}s vs ~{expected_duration:.1f}s attendu)"
                    )
                elif ratio > 2.5:
                    detail['status'] = 'too_long'
                    results['anomalies'].append(
                        f"🟡 A{ayah_num}: Trop long ({actual_duration:.1f}s vs ~{expected_duration:.1f}s attendu)"
                    )
                
                results['details'].append(detail)
    
    return results


# =============================================================================
# EXTRACTION D'IMAGES D'AYATS
# =============================================================================
_ayat_index_cache = None

def build_ayat_index(force_reload=False):
    """Construit un index des ayats vers leurs positions dans les pages.
    
    Returns:
        dict: {(surah, ayah): {"page": int, "rects": [[x,y,w,h], ...]}}
    """
    global _ayat_index_cache
    if _ayat_index_cache is not None and not force_reload:
        return _ayat_index_cache
    
    index = {}
    pattern = os.path.join(Config.ANNOTATIONS_DIR, "page_*.json")
    
    for json_path in sorted(glob.glob(pattern)):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            page_num = data.get('metadata', {}).get('page', 0)
            
            for ayat in data.get('ayats', []):
                surah = ayat.get('sourat_num', 0)
                ayah_str = ayat.get('ayah', '0')
                
                # Convertir ayah en int - "basmala" devient 0
                if ayah_str == "basmala":
                    ayah = 0  # Basmala = ayah 0
                else:
                    try:
                        ayah = int(ayah_str)
                    except:
                        continue
                
                rects = [r.get('coords', []) for r in ayat.get('rects', [])]
                
                key = (surah, ayah)
                if key not in index:
                    index[key] = {"page": page_num, "rects": rects}
                else:
                    # Ayat continue sur plusieurs pages - ajouter les rects
                    index[key]["rects"].extend(rects)
        except Exception as e:
            pass  # Ignorer les erreurs de lecture
    
    _ayat_index_cache = index
    return index

def build_juz_ayat_list(juz_num: int) -> list:
    """Construit la liste ordonnée des ayats d'un Juz.
    
    Returns:
        Liste de tuples (surah, ayah) dans l'ordre du Juz
    """
    ayat_list = []
    seen = set()
    
    # Parcourir toutes les annotations
    annotation_files = sorted(glob.glob(os.path.join(Config.ANNOTATIONS_DIR, "page_*.json")))
    
    for annot_path in annotation_files:
        try:
            with open(annot_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Vérifier si cette page appartient au Juz demandé
            page_juz = data.get("metadata", {}).get("juz", 0)
            if page_juz != juz_num:
                continue
            
            page_num = data.get("metadata", {}).get("page", 0)
            
            # Ajouter les ayats de cette page
            for ayat_info in data.get("ayats", []):
                surah = ayat_info.get("sourat_num", 0)
                ayah_str = str(ayat_info.get("ayah", "")).lower()
                
                if ayah_str == "basmala":
                    ayah = 0
                else:
                    try:
                        ayah = int(ayah_str)
                    except:
                        continue
                
                key = (surah, ayah)
                if key not in seen:
                    seen.add(key)
                    ayat_list.append(key)
        except:
            pass
    
    return ayat_list

def extract_ayat_image(surah: int, ayah: int, index: dict = None):
    """Extrait l'image d'un ayat depuis la page du Mushaf.
    
    Extrait chaque rectangle séparément et les empile verticalement
    pour éviter d'inclure des parties d'autres ayats.
    
    Args:
        surah: Numéro de sourate
        ayah: Numéro d'ayat
        index: Index des ayats (optionnel, sera construit si absent)
    
    Returns:
        QPixmap ou None si non trouvé
    """
    from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor
    from PyQt6.QtCore import QRect
    
    if index is None:
        index = build_ayat_index()
    
    key = (surah, ayah)
    if key not in index:
        return None
    
    info = index[key]
    page_num = info['page']
    rects = info['rects']
    
    # Charger l'image de la page
    page_path = os.path.join(Config.IMAGES_DIR, f"page_{page_num:03d}.png")
    if not os.path.exists(page_path):
        return None
    
    page_img = QImage(page_path)
    if page_img.isNull():
        return None
    
    if not rects:
        return None
    
    # Filtrer les rectangles valides et les trier par position Y
    valid_rects = [r for r in rects if len(r) >= 4]
    if not valid_rects:
        return None
    
    # Trier par Y (ligne) puis par X
    valid_rects.sort(key=lambda r: (r[1], -r[0]))  # Y croissant, X décroissant (droite à gauche pour l'arabe)
    
    # Extraire chaque rectangle séparément
    cropped_images = []
    margin = 5
    min_crop_height = 110  # Hauteur minimale pour la capture (polygones ~105)
    
    for rect in valid_rects:
        x, y, w, h = rect[0], rect[1], rect[2], rect[3]
        
        # Ajouter une marge
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(page_img.width(), x + w + margin)
        y2 = min(page_img.height(), y + h + margin)
        
        # Si la hauteur est trop petite (marge tronquée en haut), compenser en bas
        current_h = y2 - y1
        if current_h < min_crop_height and y2 < page_img.height():
            y2 = min(page_img.height(), y2 + (min_crop_height - current_h))
        
        cropped = page_img.copy(x1, y1, x2 - x1, y2 - y1)
        if not cropped.isNull():
            cropped_images.append(cropped)
    
    if not cropped_images:
        return None
    
    # Si un seul rectangle, retourner directement
    if len(cropped_images) == 1:
        return QPixmap.fromImage(cropped_images[0])
    
    # Calculer la taille totale pour l'image composite
    total_height = sum(img.height() for img in cropped_images) + (len(cropped_images) - 1) * 3
    max_width = max(img.width() for img in cropped_images)
    
    # Créer l'image composite avec fond blanc
    composite = QImage(max_width, total_height, QImage.Format.Format_RGB32)
    composite.fill(QColor(255, 255, 255))
    
    # Dessiner chaque image
    painter = QPainter(composite)
    current_y = 0
    
    for img in cropped_images:
        # Centrer horizontalement (ou aligner à droite pour l'arabe)
        x_offset = max_width - img.width()  # Aligner à droite
        painter.drawImage(x_offset, current_y, img)
        current_y += img.height() + 3  # Espacement entre les lignes
    
    painter.end()
    
    return QPixmap.fromImage(composite)

def extract_ayat_partial_image(surah: int, ayah: int, mode: str = "all", index: dict = None):
    """Extrait une partie d'un ayat (premier polygone, dernier, ou tous).
    
    Args:
        surah: Numéro de sourate
        ayah: Numéro d'ayat
        mode: "all" = tous les polygones, "first" = premier polygone, "last" = dernier polygone
        index: Index des ayats (optionnel)
    
    Returns:
        QPixmap ou None
    """
    from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor
    
    if index is None:
        index = build_ayat_index()
    
    key = (surah, ayah)
    if key not in index:
        return None
    
    info = index[key]
    page_num = info['page']
    rects = info['rects']
    
    page_path = os.path.join(Config.IMAGES_DIR, f"page_{page_num:03d}.png")
    if not os.path.exists(page_path):
        return None
    
    page_img = QImage(page_path)
    if page_img.isNull():
        return None
    
    valid_rects = [r for r in rects if len(r) >= 4]
    if not valid_rects:
        return None
    
    # Trier par Y (ligne) puis par X décroissant
    valid_rects.sort(key=lambda r: (r[1], -r[0]))
    
    # Sélectionner les rectangles selon le mode
    if mode == "first":
        selected_rects = [valid_rects[0]]
    elif mode == "last":
        selected_rects = [valid_rects[-1]]
    else:
        selected_rects = valid_rects
    
    # Extraire chaque rectangle
    cropped_images = []
    margin = 5
    min_crop_height = 110
    
    for rect in selected_rects:
        x, y, w, h = rect[0], rect[1], rect[2], rect[3]
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(page_img.width(), x + w + margin)
        y2 = min(page_img.height(), y + h + margin)
        
        current_h = y2 - y1
        if current_h < min_crop_height and y2 < page_img.height():
            y2 = min(page_img.height(), y2 + (min_crop_height - current_h))
        
        cropped = page_img.copy(x1, y1, x2 - x1, y2 - y1)
        if not cropped.isNull():
            cropped_images.append(cropped)
    
    if not cropped_images:
        return None
    
    if len(cropped_images) == 1:
        return QPixmap.fromImage(cropped_images[0])
    
    total_height = sum(img.height() for img in cropped_images) + (len(cropped_images) - 1) * 3
    max_width = max(img.width() for img in cropped_images)
    
    composite = QImage(max_width, total_height, QImage.Format.Format_RGB32)
    composite.fill(QColor(255, 255, 255))
    
    painter = QPainter(composite)
    current_y = 0
    for img in cropped_images:
        x_offset = max_width - img.width()
        painter.drawImage(x_offset, current_y, img)
        current_y += img.height() + 3
    painter.end()
    
    return QPixmap.fromImage(composite)


def get_cached_ayat_image(surah: int, ayah: int, force_refresh: bool = False):
    """Récupère ou crée une image d'ayat depuis le cache."""
    from PyQt6.QtGui import QPixmap
    
    # Créer le dossier cache si nécessaire
    os.makedirs(Config.AYAT_CACHE_DIR, exist_ok=True)
    
    cache_path = os.path.join(Config.AYAT_CACHE_DIR, f"s{surah:03d}_a{ayah:03d}.png")
    
    # Vérifier le cache (sauf si force_refresh)
    if not force_refresh and os.path.exists(cache_path):
        pixmap = QPixmap(cache_path)
        if not pixmap.isNull():
            return pixmap
    
    # Extraire et sauvegarder
    pixmap = extract_ayat_image(surah, ayah)
    if pixmap and not pixmap.isNull():
        pixmap.save(cache_path, "PNG")
    
    return pixmap


# =============================================================================
# WORKER THREAD - Traitement audio en arrière-plan
# =============================================================================
class AudioSplitterWorker(QThread):
    """Thread de traitement pour la segmentation audio."""
    
    # Signaux pour communiquer avec l'interface
    progress = pyqtSignal(int, str)           # (pourcentage, message)
    segment_found = pyqtSignal(int, int, int, int) # (surah, ayah, start_ms, end_ms)
    finished = pyqtSignal(int, str)           # (nb_segments, output_dir)
    error = pyqtSignal(str)                   # message d'erreur
    cancelled = pyqtSignal()                  # signal d'annulation
    
    def __init__(self, audio_path: str, output_dir: str,
                 surah_num: int, start_ayah: int, limit: int,
                 silence_thresh: int, min_silence_len: int, keep_silence: int,
                 juz_mode: bool = False, juz_num: int = 30):
        super().__init__()
        self.audio_path = audio_path
        self.output_dir = output_dir
        self.surah_num = surah_num
        self.start_ayah = start_ayah
        self.limit = limit  # 0 = pas de limite
        self.silence_thresh = silence_thresh
        self.min_silence_len = min_silence_len
        self.keep_silence = keep_silence
        self.juz_mode = juz_mode  # Mode multi-sourate
        self.juz_num = juz_num    # Numéro du Juz
        self._is_cancelled = False
    
    def cancel(self):
        """Annule le traitement en cours."""
        self._is_cancelled = True
    
    def run(self):
        """Exécute la segmentation audio."""
        try:
            # 1. Chargement du fichier audio
            self.progress.emit(5, "Chargement du fichier audio...")
            audio = AudioSegment.from_file(self.audio_path)
            
            if self._is_cancelled:
                self.cancelled.emit()
                return
            
            # Calculer la durée pour info
            duration_sec = len(audio) / 1000
            duration_min = int(duration_sec // 60)
            duration_str = f"{duration_min}min" if duration_min > 0 else f"{int(duration_sec)}s"
            
            # 2. Détection des segments non-silencieux
            self.progress.emit(10, f"⏳ Analyse en cours ({duration_str})... Patientez")
            nonsilent_ranges = detect_nonsilent(
                audio,
                min_silence_len=self.min_silence_len,
                silence_thresh=self.silence_thresh
            )
            
            if self._is_cancelled:
                self.cancelled.emit()
                return
            
            if not nonsilent_ranges:
                self.error.emit("Aucun segment détecté. Ajustez les paramètres.")
                return
            
            # Appliquer la limite si définie
            if self.limit > 0:
                nonsilent_ranges = nonsilent_ranges[:self.limit]
            
            # Émettre les segments trouvés avec numéros d'ayat
            for i, (start, end) in enumerate(nonsilent_ranges):
                ayah_num = self.start_ayah + i
                self.segment_found.emit(self.surah_num, ayah_num, start, end)
            
            # 3. Création du dossier de sortie
            if self.juz_mode:
                # Mode Juz: dossier temporaire nommé juz_XX_temp
                surah_dir = os.path.join(self.output_dir, f"juz_{self.juz_num:02d}_temp")
            else:
                # Mode normal: dossier par sourate
                surah_dir = os.path.join(self.output_dir, f"{self.surah_num:03d}")
            os.makedirs(surah_dir, exist_ok=True)
            
            # 4. Export des segments
            total = len(nonsilent_ranges)
            
            for i, (start_ms, end_ms) in enumerate(nonsilent_ranges):
                if self._is_cancelled:
                    self.cancelled.emit()
                    return
                
                ayah_num = self.start_ayah + i
                
                # Ajouter du silence aux bords
                start_with_silence = max(0, start_ms - self.keep_silence)
                end_with_silence = min(len(audio), end_ms + self.keep_silence)
                
                # Extraire le segment
                segment = audio[start_with_silence:end_with_silence]
                
                # Sauvegarder avec nom = numéro d'ayat
                output_path = os.path.join(surah_dir, f"{ayah_num:03d}.mp3")
                segment.export(output_path, format="mp3")
                
                # Mise à jour de la progression
                progress = 20 + int(80 * (i + 1) / total)
                self.progress.emit(progress, f"S{self.surah_num}:A{ayah_num} ({i+1}/{total})")
            
            self.finished.emit(total, self.output_dir)
            
        except Exception as e:
            self.error.emit(f"Erreur: {str(e)}")


# =============================================================================
# DIALOGUE DE PRÉVISUALISATION POUR DIVISION
# =============================================================================
class SplitPreviewDialog(QDialog):
    """Dialogue pour prévisualiser et marquer le point de coupure."""
    
    def __init__(self, audio_path: str, surah: int, ayah: int, parent=None):
        super().__init__(parent)
        self.audio_path = audio_path
        self.surah = surah
        self.ayah = ayah
        self.split_point = None
        self.duration_ms = 0
        self.preview_mode = None  # "part1" ou "part2"
        self.preview_end_ms = 0
        
        self.setWindowTitle("✂️ Diviser le segment")
        self.setMinimumSize(650, 600)
        self.resize(720, 650)
        
        self._setup_ui()
        self._setup_player()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Info sur le segment
        info_label = QLabel(f"📄 Segment: {os.path.basename(self.audio_path)}")
        info_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(info_label)
        
        # Zone d'images des polygones (scrollable)
        img_scroll = QScrollArea()
        img_scroll.setWidgetResizable(True)
        img_scroll.setMaximumHeight(460)
        img_scroll.setStyleSheet("QScrollArea { border: 1px solid #ddd; background: #f9f9f9; border-radius: 5px; }")
        
        img_widget = QWidget()
        img_layout = QVBoxLayout(img_widget)
        img_layout.setContentsMargins(10, 10, 10, 10)
        img_layout.setSpacing(8)
        img_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Charger l'index des ayats
        ayat_index = build_ayat_index()
        
        # --- Dernier polygone de l'ayat précédente ---
        if self.ayah > 0:
            prev_pixmap = extract_ayat_partial_image(self.surah, self.ayah - 1, mode="last", index=ayat_index)
            if prev_pixmap:
                prev_container = QWidget()
                prev_container.setStyleSheet("background: #e8f5e9; border-radius: 4px;")
                prev_lay = QVBoxLayout(prev_container)
                prev_lay.setContentsMargins(6, 6, 6, 6)
                prev_title = QLabel("↩️ Dernier polygone - Ayat précédente")
                prev_title.setStyleSheet("font-size: 11px; color: #2e7d32; font-weight: bold;")
                prev_lay.addWidget(prev_title)
                prev_img = QLabel()
                prev_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
                prev_img.setPixmap(prev_pixmap.scaledToWidth(380, Qt.TransformationMode.SmoothTransformation))
                prev_lay.addWidget(prev_img)
                img_layout.addWidget(prev_container)
        
        # --- Tous les polygones de l'ayat cible ---
        curr_pixmap = extract_ayat_partial_image(self.surah, self.ayah, mode="all", index=ayat_index)
        if curr_pixmap:
            curr_container = QWidget()
            curr_container.setStyleSheet("background: #fff9e6; border-radius: 4px;")
            curr_lay = QVBoxLayout(curr_container)
            curr_lay.setContentsMargins(6, 6, 6, 6)
            curr_title = QLabel("📖 Ayat à diviser (tous les polygones)")
            curr_title.setStyleSheet("font-size: 11px; color: #e65100; font-weight: bold;")
            curr_lay.addWidget(curr_title)
            curr_img = QLabel()
            curr_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            curr_img.setPixmap(curr_pixmap.scaledToWidth(380, Qt.TransformationMode.SmoothTransformation))
            curr_lay.addWidget(curr_img)
            img_layout.addWidget(curr_container)
        
        # --- Premier polygone de l'ayat suivante ---
        next_pixmap = extract_ayat_partial_image(self.surah, self.ayah + 1, mode="first", index=ayat_index)
        if next_pixmap:
            next_container = QWidget()
            next_container.setStyleSheet("background: #e3f2fd; border-radius: 4px;")
            next_lay = QVBoxLayout(next_container)
            next_lay.setContentsMargins(6, 6, 6, 6)
            next_title = QLabel("↪️ Premier polygone - Ayat suivante")
            next_title.setStyleSheet("font-size: 11px; color: #1565c0; font-weight: bold;")
            next_lay.addWidget(next_title)
            next_img = QLabel()
            next_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            next_img.setPixmap(next_pixmap.scaledToWidth(380, Qt.TransformationMode.SmoothTransformation))
            next_lay.addWidget(next_img)
            img_layout.addWidget(next_container)
        
        img_scroll.setWidget(img_widget)
        layout.addWidget(img_scroll)
        
        layout.addSpacing(5)
        
        # Barre de progression audio
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(self._seek_position)
        layout.addWidget(self.position_slider)
        
        # Labels de temps
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("0:00.0")
        self.current_time_label.setStyleSheet("font-family: monospace; font-size: 14px;")
        self.duration_label = QLabel("/ 0:00.0")
        self.duration_label.setStyleSheet("font-family: monospace; color: gray;")
        time_layout.addWidget(self.current_time_label)
        time_layout.addWidget(self.duration_label)
        time_layout.addStretch()
        layout.addLayout(time_layout)
        
        layout.addSpacing(10)
        
        # Contrôles de lecture
        playback_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("▶️ Lecture")
        self.play_btn.clicked.connect(self._toggle_play)
        playback_layout.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.clicked.connect(self._stop)
        playback_layout.addWidget(self.stop_btn)
        
        playback_layout.addSpacing(20)
        
        self.mark_btn = QPushButton("✂️ Marquer ici")
        self.mark_btn.setStyleSheet("background-color: #ff6600; color: white; font-weight: bold; padding: 8px 16px;")
        self.mark_btn.clicked.connect(self._mark_split_point)
        playback_layout.addWidget(self.mark_btn)
        
        playback_layout.addStretch()
        layout.addLayout(playback_layout)
        
        layout.addSpacing(15)
        
        # Point de coupure manuel
        split_layout = QHBoxLayout()
        split_layout.addWidget(QLabel("Point de coupure (secondes):"))
        
        self.split_spin = QDoubleSpinBox()
        self.split_spin.setRange(0.1, 999.9)
        self.split_spin.setDecimals(1)
        self.split_spin.setSingleStep(0.1)
        self.split_spin.setValue(0.0)
        self.split_spin.setStyleSheet("font-size: 14px; padding: 4px;")
        split_layout.addWidget(self.split_spin)
        
        self.split_marked_label = QLabel("")
        self.split_marked_label.setStyleSheet("color: #ff6600; font-weight: bold;")
        split_layout.addWidget(self.split_marked_label)
        
        split_layout.addStretch()
        layout.addLayout(split_layout)
        
        layout.addSpacing(10)
        
        # Boutons de prévisualisation des parties
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(QLabel("🔊 Vérifier:"))
        
        self.preview_part1_btn = QPushButton("▶️ Partie 1 (avant)")
        self.preview_part1_btn.setStyleSheet("background-color: #4a90d9; color: white; padding: 6px 12px;")
        self.preview_part1_btn.clicked.connect(self._preview_part1)
        preview_layout.addWidget(self.preview_part1_btn)
        
        self.preview_part2_btn = QPushButton("▶️ Partie 2 (après)")
        self.preview_part2_btn.setStyleSheet("background-color: #9b59b6; color: white; padding: 6px 12px;")
        self.preview_part2_btn.clicked.connect(self._preview_part2)
        preview_layout.addWidget(self.preview_part2_btn)
        
        self.preview_status_label = QLabel("")
        self.preview_status_label.setStyleSheet("color: #666; font-style: italic;")
        preview_layout.addWidget(self.preview_status_label)
        
        preview_layout.addStretch()
        layout.addLayout(preview_layout)
        
        layout.addSpacing(15)
        
        # Boutons OK/Annuler
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("✅ Diviser à ce point")
        ok_btn.setStyleSheet("background-color: #00aa00; color: white; font-weight: bold; padding: 8px 16px;")
        ok_btn.clicked.connect(self._accept_split)
        buttons_layout.addWidget(ok_btn)
        
        layout.addLayout(buttons_layout)
    
    def _setup_player(self):
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)
        
        self.media_player.setSource(QUrl.fromLocalFile(self.audio_path))
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.playbackStateChanged.connect(self._on_state_changed)
    
    def _on_duration_changed(self, duration):
        self.duration_ms = duration
        self.position_slider.setRange(0, duration)
        
        secs = duration / 1000
        mins = int(secs // 60)
        secs = secs % 60
        self.duration_label.setText(f"/ {mins}:{secs:04.1f}")
        
        # Mettre le spin au milieu par défaut
        self.split_spin.setMaximum(duration / 1000 - 0.1)
        self.split_spin.setValue(duration / 2000)
    
    def _on_position_changed(self, position):
        self.position_slider.setValue(position)
        
        secs = position / 1000
        mins = int(secs // 60)
        secs = secs % 60
        self.current_time_label.setText(f"{mins}:{secs:04.1f}")
        
        # Vérifier si on doit arrêter la prévisualisation
        self._check_preview_end(position)
    
    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("⏸️ Pause")
        else:
            self.play_btn.setText("▶️ Lecture")
            # Réinitialiser les boutons de prévisualisation si arrêté
            if state == QMediaPlayer.PlaybackState.StoppedState:
                self._reset_preview_buttons()
    
    def _seek_position(self, position):
        self.media_player.setPosition(position)
    
    def _toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()
    
    def _stop(self):
        self.media_player.stop()
        self.preview_mode = None
        self.preview_status_label.setText("")
    
    def _preview_part1(self):
        """Joue la partie 1 (du début au point de coupure)."""
        split_ms = int(self.split_spin.value() * 1000)
        if split_ms <= 0:
            self.preview_status_label.setText("⚠️ Définissez d'abord le point de coupure")
            return
        
        self.preview_mode = "part1"
        self.preview_end_ms = split_ms
        self.media_player.setPosition(0)
        self.media_player.play()
        
        split_sec = split_ms / 1000
        self.preview_status_label.setText(f"🔊 Partie 1: 0s → {split_sec:.1f}s")
        self.preview_part1_btn.setText("⏸️ Partie 1...")
        self.preview_part2_btn.setEnabled(False)
    
    def _preview_part2(self):
        """Joue la partie 2 (du point de coupure à la fin)."""
        split_ms = int(self.split_spin.value() * 1000)
        if split_ms <= 0:
            self.preview_status_label.setText("⚠️ Définissez d'abord le point de coupure")
            return
        
        self.preview_mode = "part2"
        self.preview_end_ms = self.duration_ms
        self.media_player.setPosition(split_ms)
        self.media_player.play()
        
        split_sec = split_ms / 1000
        duration_sec = self.duration_ms / 1000
        self.preview_status_label.setText(f"🔊 Partie 2: {split_sec:.1f}s → {duration_sec:.1f}s")
        self.preview_part2_btn.setText("⏸️ Partie 2...")
        self.preview_part1_btn.setEnabled(False)
    
    def _check_preview_end(self, position):
        """Vérifie si la prévisualisation doit s'arrêter."""
        if self.preview_mode == "part1" and position >= self.preview_end_ms:
            self.media_player.pause()
            self._reset_preview_buttons()
            self.preview_status_label.setText("✓ Partie 1 terminée")
    
    def _reset_preview_buttons(self):
        """Réinitialise les boutons de prévisualisation."""
        self.preview_mode = None
        self.preview_part1_btn.setText("▶️ Partie 1 (avant)")
        self.preview_part2_btn.setText("▶️ Partie 2 (après)")
        self.preview_part1_btn.setEnabled(True)
        self.preview_part2_btn.setEnabled(True)
    
    def _mark_split_point(self):
        """Marque le point de coupure à la position actuelle."""
        position_ms = self.media_player.position()
        position_sec = position_ms / 1000
        
        self.split_spin.setValue(position_sec)
        self.split_marked_label.setText(f"✓ Marqué à {position_sec:.1f}s")
        
        # Pause pour permettre d'ajuster si nécessaire
        self.media_player.pause()
    
    def _accept_split(self):
        """Accepte le point de coupure et ferme le dialogue."""
        self.split_point = self.split_spin.value()
        
        if self.split_point < 0.1 or self.split_point >= (self.duration_ms / 1000 - 0.1):
            QMessageBox.warning(
                self, "Point invalide",
                f"Le point de coupure doit être entre 0.1s et {self.duration_ms/1000 - 0.1:.1f}s"
            )
            return
        
        self.media_player.stop()
        self.accept()
    
    def get_split_point(self) -> float:
        """Retourne le point de coupure en secondes."""
        return self.split_point
    
    def closeEvent(self, event):
        self.media_player.stop()
        super().closeEvent(event)


# =============================================================================
# DIALOGUE POUR RÉCUPÉRER UN SEGMENT PERDU
# =============================================================================
class RecoverSegmentDialog(QDialog):
    """Dialogue avancé pour récupérer et insérer un segment manquant."""
    
    def __init__(self, output_dir: str, backup_history: list, parent=None):
        super().__init__(parent)
        self.output_dir = output_dir
        self.backup_history = backup_history
        self.audio_path = None
        self.trimmed_audio = None
        self.split_segments = []  # Liste de tuples (AudioSegment, start_ms, end_ms)
        self.selected_segment = None
        self.insert_position = None
        
        # Estimer le segment perdu
        self.estimated_start = 0
        self.estimated_end = 0
        self._estimate_lost_segment()
        
        self.setWindowTitle("🔧 Récupérer un segment perdu")
        self.setMinimumSize(700, 600)
        self.resize(800, 700)
        
        self._setup_ui()
        self._setup_player()
    
    def _estimate_lost_segment(self):
        """Estime le temps du segment perdu à partir de l'historique."""
        if not self.backup_history:
            return
        
        # Calculer le temps total des segments avant le segment perdu
        all_files = sorted(glob.glob(os.path.join(self.output_dir, "[0-9][0-9][0-9].mp3")))
        
        total_ms = 0
        for mp3_file in all_files:
            try:
                audio = AudioSegment.from_file(mp3_file)
                total_ms += len(audio)
            except:
                pass
        
        # Utiliser le dernier backup pour estimer
        if self.backup_history:
            last_backup = self.backup_history[-1]
            if 'files' in last_backup and last_backup['files']:
                # Estimer autour du segment fusionné
                for file_info in last_backup['files']:
                    try:
                        backup_path = file_info.get('backup', '')
                        if os.path.exists(backup_path):
                            audio = AudioSegment.from_file(backup_path)
                            # Le segment perdu est probablement autour d'ici
                            self.estimated_start = max(0, total_ms - 60000)  # 1 min avant
                            self.estimated_end = total_ms + 60000  # 1 min après
                            break
                    except:
                        pass
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Section 1: Charger l'audio source ---
        source_group = QGroupBox("1️⃣ Audio source")
        source_layout = QVBoxLayout(source_group)
        
        load_layout = QHBoxLayout()
        self.source_label = QLabel("Aucun fichier chargé")
        self.source_label.setStyleSheet("color: gray;")
        load_layout.addWidget(self.source_label, 1)
        
        load_btn = QPushButton("📂 Charger audio original")
        load_btn.clicked.connect(self._load_source_audio)
        load_layout.addWidget(load_btn)
        source_layout.addLayout(load_layout)
        
        # Lecteur audio
        player_layout = QHBoxLayout()
        
        rewind_btn = QPushButton("⏪ -20s")
        rewind_btn.clicked.connect(lambda: self._skip_seconds(-20))
        player_layout.addWidget(rewind_btn)
        
        self.play_source_btn = QPushButton("▶️ Lecture")
        self.play_source_btn.setEnabled(False)
        self.play_source_btn.clicked.connect(self._toggle_play)
        player_layout.addWidget(self.play_source_btn)
        
        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.clicked.connect(self._stop_playback)
        player_layout.addWidget(self.stop_btn)
        
        forward_btn = QPushButton("+20s ⏩")
        forward_btn.clicked.connect(lambda: self._skip_seconds(20))
        player_layout.addWidget(forward_btn)
        
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(self._seek_position)
        player_layout.addWidget(self.position_slider, 1)
        
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet("font-family: monospace;")
        player_layout.addWidget(self.time_label)
        source_layout.addLayout(player_layout)
        
        layout.addWidget(source_group)
        
        # --- Section 2: Définir la zone à extraire ---
        zone_group = QGroupBox("2️⃣ Zone à extraire (position ± marge)")
        zone_layout = QVBoxLayout(zone_group)
        
        # Estimation
        estimate_layout = QHBoxLayout()
        self.estimate_label = QLabel("⏱️ Saisissez la position estimée du segment perdu")
        self.estimate_label.setStyleSheet("color: #666; font-style: italic;")
        estimate_layout.addWidget(self.estimate_label)
        zone_layout.addLayout(estimate_layout)
        
        # Position et marge
        times_layout = QHBoxLayout()
        times_layout.addWidget(QLabel("Position (mm:ss):"))
        
        self.position_min_spin = QSpinBox()
        self.position_min_spin.setRange(0, 999)
        self.position_min_spin.setValue(int(self.estimated_start / 60000))
        self.position_min_spin.setSuffix(" min")
        times_layout.addWidget(self.position_min_spin)
        
        self.position_sec_spin = QSpinBox()
        self.position_sec_spin.setRange(0, 59)
        self.position_sec_spin.setValue(0)
        self.position_sec_spin.setSuffix(" sec")
        times_layout.addWidget(self.position_sec_spin)
        
        times_layout.addSpacing(30)
        times_layout.addWidget(QLabel("Marge:"))
        
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(1, 10)
        self.margin_spin.setValue(1)
        self.margin_spin.setSuffix(" min")
        times_layout.addWidget(self.margin_spin)
        
        times_layout.addStretch()
        zone_layout.addLayout(times_layout)
        
        # Affichage de la zone calculée
        calc_layout = QHBoxLayout()
        self.calc_label = QLabel("📍 Zone: 0:00 → 2:00")
        self.calc_label.setStyleSheet("color: #2980b9; font-weight: bold;")
        calc_layout.addWidget(self.calc_label)
        calc_layout.addStretch()
        zone_layout.addLayout(calc_layout)
        
        # Mettre à jour l'affichage quand les valeurs changent
        self.position_min_spin.valueChanged.connect(self._update_zone_display)
        self.position_sec_spin.valueChanged.connect(self._update_zone_display)
        self.margin_spin.valueChanged.connect(self._update_zone_display)
        self._update_zone_display()
        
        # Bouton pour aller à cette position
        nav_layout = QHBoxLayout()
        goto_btn = QPushButton("🎯 Aller à cette position")
        goto_btn.clicked.connect(self._goto_position)
        nav_layout.addWidget(goto_btn)
        
        mark_btn = QPushButton("📍 Marquer position actuelle")
        mark_btn.clicked.connect(self._mark_current_position)
        nav_layout.addWidget(mark_btn)
        
        nav_layout.addStretch()
        zone_layout.addLayout(nav_layout)
        
        # Bouton extraire
        extract_layout = QHBoxLayout()
        self.extract_btn = QPushButton("✂️ Extraire cette zone")
        self.extract_btn.setEnabled(False)
        self.extract_btn.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold; padding: 8px;")
        self.extract_btn.clicked.connect(self._extract_zone)
        extract_layout.addWidget(self.extract_btn)
        extract_layout.addStretch()
        zone_layout.addLayout(extract_layout)
        
        layout.addWidget(zone_group)
        
        # --- Section 3: Découper la zone extraite ---
        split_group = QGroupBox("3️⃣ Découper en segments")
        split_layout = QVBoxLayout(split_group)
        
        # Paramètres de détection
        params_layout = QHBoxLayout()
        params_layout.addWidget(QLabel("Seuil silence (dB):"))
        self.thresh_spin = QSpinBox()
        self.thresh_spin.setRange(-60, -20)
        self.thresh_spin.setValue(-40)
        params_layout.addWidget(self.thresh_spin)
        
        params_layout.addWidget(QLabel("Min silence (ms):"))
        self.min_silence_spin = QSpinBox()
        self.min_silence_spin.setRange(100, 2000)
        self.min_silence_spin.setValue(500)
        params_layout.addWidget(self.min_silence_spin)
        
        self.split_btn = QPushButton("🔪 Découper")
        self.split_btn.setEnabled(False)
        self.split_btn.clicked.connect(self._split_zone)
        params_layout.addWidget(self.split_btn)
        
        params_layout.addStretch()
        split_layout.addLayout(params_layout)
        
        # Liste des segments découpés
        self.segments_list = QListWidget()
        self.segments_list.setMaximumHeight(150)
        self.segments_list.itemClicked.connect(self._on_segment_selected)
        self.segments_list.itemDoubleClicked.connect(self._play_selected_segment)
        split_layout.addWidget(self.segments_list)
        
        layout.addWidget(split_group)
        
        # --- Section 4: Insérer le segment ---
        insert_group = QGroupBox("4️⃣ Insérer le segment sélectionné")
        insert_layout = QHBoxLayout(insert_group)
        
        insert_layout.addWidget(QLabel("Insérer à la position:"))
        self.position_spin = QSpinBox()
        self.position_spin.setRange(1, 999)
        self.position_spin.setValue(1)
        insert_layout.addWidget(self.position_spin)
        
        insert_layout.addWidget(QLabel("(ex: 37 pour insérer comme fichier 037.mp3)"))
        
        insert_layout.addStretch()
        
        self.insert_btn = QPushButton("✅ Insérer ce segment")
        self.insert_btn.setEnabled(False)
        self.insert_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 8px 16px;")
        self.insert_btn.clicked.connect(self._insert_segment)
        insert_layout.addWidget(self.insert_btn)
        
        layout.addWidget(insert_group)
        
        # --- Boutons fermer ---
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.close)
        buttons_layout.addWidget(close_btn)
        layout.addLayout(buttons_layout)
    
    def _setup_player(self):
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)
        
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.positionChanged.connect(self._on_position_changed)
    
    def _load_source_audio(self):
        from PyQt6.QtWidgets import QFileDialog
        
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Charger l'audio source (Juz complet ou Sourate)",
            "",
            "Audio (*.mp3 *.wav *.m4a *.flac);;Tous (*)"
        )
        
        if path:
            self.audio_path = path
            self.source_label.setText(os.path.basename(path))
            self.source_label.setStyleSheet("color: green; font-weight: bold;")
            
            self.media_player.setSource(QUrl.fromLocalFile(path))
            self.play_source_btn.setEnabled(True)
            self.extract_btn.setEnabled(True)
    
    def _on_duration_changed(self, duration):
        self.position_slider.setRange(0, duration)
        self.position_min_spin.setMaximum(int(duration / 60000) + 1)
        self._update_time_label()
    
    def _on_position_changed(self, position):
        self.position_slider.setValue(position)
        self._update_time_label()
    
    def _update_time_label(self):
        pos = self.media_player.position() / 1000
        dur = self.media_player.duration() / 1000
        self.time_label.setText(f"{int(pos//60)}:{int(pos%60):02d} / {int(dur//60)}:{int(dur%60):02d}")
    
    def _toggle_play(self):
        if not self.audio_path:
            QMessageBox.warning(self, "Erreur", "Chargez d'abord un fichier audio")
            return
        
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_source_btn.setText("▶️ Lecture")
        else:
            # S'assurer que la source est bien chargée
            if self.media_player.source().isEmpty():
                self.media_player.setSource(QUrl.fromLocalFile(self.audio_path))
            self.media_player.play()
            self.play_source_btn.setText("⏸️ Pause")
    
    def _stop_playback(self):
        self.media_player.stop()
        self.play_source_btn.setText("▶️ Lecture")
    
    def _seek_position(self, position):
        self.media_player.setPosition(position)
    
    def _skip_seconds(self, seconds):
        """Avance ou recule de N secondes."""
        current = self.media_player.position()
        new_pos = max(0, current + seconds * 1000)
        new_pos = min(new_pos, self.media_player.duration())
        self.media_player.setPosition(int(new_pos))
    
    def _get_position_ms(self):
        """Retourne la position en millisecondes."""
        return (self.position_min_spin.value() * 60 + self.position_sec_spin.value()) * 1000
    
    def _get_zone_bounds(self):
        """Retourne (start_ms, end_ms) de la zone à extraire."""
        position_ms = self._get_position_ms()
        margin_ms = self.margin_spin.value() * 60 * 1000
        start_ms = max(0, position_ms - margin_ms)
        end_ms = position_ms + margin_ms
        return start_ms, end_ms
    
    def _update_zone_display(self):
        """Met à jour l'affichage de la zone calculée."""
        start_ms, end_ms = self._get_zone_bounds()
        start_min = int(start_ms / 60000)
        start_sec = int((start_ms % 60000) / 1000)
        end_min = int(end_ms / 60000)
        end_sec = int((end_ms % 60000) / 1000)
        self.calc_label.setText(f"📍 Zone: {start_min}:{start_sec:02d} → {end_min}:{end_sec:02d}")
    
    def _goto_position(self):
        """Va à la position spécifiée dans le lecteur."""
        position_ms = self._get_position_ms()
        self.media_player.setPosition(int(position_ms))
    
    def _mark_current_position(self):
        """Marque la position actuelle du lecteur."""
        current_ms = self.media_player.position()
        minutes = int(current_ms / 60000)
        seconds = int((current_ms % 60000) / 1000)
        self.position_min_spin.setValue(minutes)
        self.position_sec_spin.setValue(seconds)
    
    def _extract_zone(self):
        """Extrait la zone définie de l'audio source."""
        if not self.audio_path:
            return
        
        try:
            start_ms, end_ms = self._get_zone_bounds()
            
            audio = AudioSegment.from_file(self.audio_path)
            # Limiter à la durée de l'audio
            end_ms = min(end_ms, len(audio))
            
            self.trimmed_audio = audio[start_ms:end_ms]
            
            duration = len(self.trimmed_audio) / 1000
            QMessageBox.information(
                self, "Extraction réussie",
                f"✅ Zone extraite: {duration:.1f}s\n\n"
                f"Cliquez sur '🔪 Découper' pour segmenter cette zone."
            )
            
            self.split_btn.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
    
    def _split_zone(self):
        """Découpe la zone extraite en segments."""
        if self.trimmed_audio is None:
            return
        
        try:
            thresh = self.thresh_spin.value()
            min_silence = self.min_silence_spin.value()
            
            # Détecter les parties non-silencieuses
            nonsilent_ranges = detect_nonsilent(
                self.trimmed_audio,
                min_silence_len=min_silence,
                silence_thresh=thresh
            )
            
            if not nonsilent_ranges:
                QMessageBox.warning(self, "Aucun segment", "Aucun segment détecté. Ajustez les paramètres.")
                return
            
            self.split_segments = []
            self.segments_list.clear()
            
            for i, (start_ms, end_ms) in enumerate(nonsilent_ranges):
                # Ajouter un peu de silence au début/fin
                start_ms = max(0, start_ms - 200)
                end_ms = min(len(self.trimmed_audio), end_ms + 200)
                
                segment = self.trimmed_audio[start_ms:end_ms]
                self.split_segments.append((segment, start_ms, end_ms))
                
                duration = len(segment) / 1000
                item = QListWidgetItem(f"Segment {i+1} | {duration:.1f}s | {start_ms/1000:.1f}s → {end_ms/1000:.1f}s")
                self.segments_list.addItem(item)
            
            QMessageBox.information(
                self, "Découpage terminé",
                f"✅ {len(self.split_segments)} segments trouvés.\n\n"
                f"Double-cliquez pour écouter, puis sélectionnez celui à insérer."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
    
    def _on_segment_selected(self, item):
        idx = self.segments_list.row(item)
        if 0 <= idx < len(self.split_segments):
            self.selected_segment = self.split_segments[idx][0]
            self.insert_btn.setEnabled(True)
    
    def _play_selected_segment(self, item):
        """Joue le segment sélectionné."""
        idx = self.segments_list.row(item)
        if 0 <= idx < len(self.split_segments):
            segment = self.split_segments[idx][0]
            
            # Sauvegarder temporairement pour lecture
            import tempfile
            temp_path = os.path.join(tempfile.gettempdir(), "preview_segment.mp3")
            segment.export(temp_path, format="mp3")
            
            self.media_player.setSource(QUrl.fromLocalFile(temp_path))
            self.media_player.play()
            self.play_source_btn.setText("⏸️ Pause")
    
    def _insert_segment(self):
        """Insère le segment sélectionné à la position spécifiée."""
        if self.selected_segment is None:
            QMessageBox.warning(self, "Erreur", "Sélectionnez d'abord un segment")
            return
        
        position = self.position_spin.value()
        
        try:
            # Décaler tous les fichiers >= position vers le haut
            all_files = sorted(glob.glob(os.path.join(self.output_dir, "[0-9][0-9][0-9].mp3")), reverse=True)
            
            for mp3_file in all_files:
                file_num = int(os.path.basename(mp3_file).replace(".mp3", ""))
                if file_num >= position:
                    new_num = file_num + 1
                    new_path = os.path.join(self.output_dir, f"{new_num:03d}.mp3")
                    os.rename(mp3_file, new_path)
            
            # Sauvegarder le nouveau segment
            new_path = os.path.join(self.output_dir, f"{position:03d}.mp3")
            self.selected_segment.export(new_path, format="mp3")
            
            self.insert_position = position
            
            QMessageBox.information(
                self, "Insertion réussie",
                f"✅ Segment inséré comme {position:03d}.mp3\n\n"
                f"Rechargez la liste des segments pour voir le résultat."
            )
            
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
    
    def get_insert_position(self):
        return self.insert_position
    
    def closeEvent(self, event):
        self.media_player.stop()
        super().closeEvent(event)


# =============================================================================
# INTERFACE GRAPHIQUE
# =============================================================================
class AudioSplitterWindow(QMainWindow):
    """Fenêtre principale du module de segmentation audio."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎵 Quran Audio Splitter")
        self.setMinimumSize(1400, 800)
        self.resize(1200, 850)
        
        # État
        self.current_file = None
        self.worker = None
        self.exported_segments = []  # Liste des fichiers exportés
        self.ayat_index = None  # Index pour les images d'ayats
        self.merge_history = []  # Historique pour annuler les fusions
        self.split_history = []  # Historique pour annuler les divisions
        self.transfer_history = []  # Historique pour annuler les transferts de sourate
        
        # Chronomètre
        self.elapsed_timer = QTimer()
        self.elapsed_timer.timeout.connect(self._update_elapsed_time)
        self.start_time = None
        
        # Lecteur audio
        self.audio_output = QAudioOutput()
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.media_player.positionChanged.connect(self._on_playback_position_changed)
        self.media_player.durationChanged.connect(self._on_playback_duration_changed)
        self.playing_row = -1  # Ligne en cours de lecture
        self.playing_duration = 0  # Durée du segment en cours
        
        # Auto-play (lecture automatique ayat après ayat)
        self.auto_play_enabled = False
        self.auto_deselect_after_play = False  # Désélectionner après lecture post-fusion
        self.playback_multi_select_mode = False  # True = garder les segments sélectionnés en lecture auto
        
        # Vitesse du défilement auto du panneau de prévisualisation
        # 1.0 = arrive en bas à la fin de l'audio
        # 1.5 = arrive en bas à ~66% de l'audio (plus rapide)
        # 2.0 = arrive en bas à 50% de l'audio (encore plus rapide)
        # 0.5 = arrive en bas à 2x la durée (plus lent)
        self.SCROLL_SPEED_FACTOR = 1.0
        
        self.auto_play_timer = QTimer()
        self.auto_play_timer.setSingleShot(True)
        self.auto_play_timer.timeout.connect(self._play_next_segment)
        
        # Mode Juz (multi-sourate)
        self.juz_mode = False
        self.juz_num = 30  # Numéro du Juz par défaut
        self.juz_ayat_list = []  # Liste ordonnée des ayats du Juz
        self.skip_istiadha = False  # Ignorer le premier segment (Isti'adha)
        
        # Segments marqués (bookmarks) pour retrouver rapidement un ayat sur plusieurs morceaux
        self.bookmarked_rows: set[int] = set()
        
        # Construction de l'interface
        self._setup_ui()
        
        # Vérifier s'il y a une session précédente à restaurer
        # (après un délai pour laisser l'interface s'afficher)
        QTimer.singleShot(500, self._check_and_restore_session)
        
        # Vérifier les sourates déjà traitées sur Hugging Face (async)
        QTimer.singleShot(1000, self._check_hf_sync_on_startup)
    
    # -------------------------------------------------------------------------
    # Méthodes utilitaires
    # -------------------------------------------------------------------------
    
    def _get_output_dir(self) -> str:
        """
        Retourne le chemin du dossier de sortie selon le mode actuel.
        
        Returns:
            Chemin du dossier de sortie (juz_XX_temp ou XXX)
        """
        if self.juz_mode:
            return os.path.join(Config.AUDIO_OUTPUT_DIR, f"juz_{self.juz_num:02d}_temp")
        return os.path.join(Config.AUDIO_OUTPUT_DIR, f"{self.surah_spin.value():03d}")
    
    def _check_hf_sync_on_startup(self):
        """Vérifie au démarrage quelles sourates sont déjà traitées sur HF et localement."""
        # Vérification locale (rapide)
        local_done = get_local_completed_surahs()
        
        # Vérification distante (peut être lente)
        remote_done = get_remote_completed_surahs()
        
        # Fusionner les deux sets
        self._completed_surahs = local_done | remote_done
        
        if self._completed_surahs:
            # Formater le message
            surah_list = sorted(self._completed_surahs)
            if len(surah_list) <= 10:
                surah_str = ", ".join(str(s) for s in surah_list)
            else:
                surah_str = ", ".join(str(s) for s in surah_list[:10]) + f" ... et {len(surah_list)-10} autres"
            
            # Déterminer d'où viennent les données
            sources = []
            if local_done:
                sources.append(f"{len(local_done)} locale(s)")
            if remote_done:
                sources.append(f"{len(remote_done)} sur HF")
            source_str = " + ".join(sources)
            
            QMessageBox.information(
                self,
                "📋 Sourates déjà traitées",
                f"{len(self._completed_surahs)} sourate(s) déjà segmentée(s) ({source_str}).\n\n"
                f"Sourates: {surah_str}\n\n"
                f"💡 Ces sourates sont verrouillées.\n"
                f"   Utilisez le panneau Admin (🔧) pour les gérer."
            )
        else:
            self._completed_surahs = set()
    
    def _upload_current_surah(self):
        """Upload la sourate actuelle vers Hugging Face."""
        if self.juz_mode:
            QMessageBox.warning(self, "Mode Juz", "L'upload n'est pas disponible en mode Juz.\nUtilisez 'Transférer' puis uploadez chaque sourate.")
            return
        
        surah_num = self.surah_spin.value()
        surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{surah_num:03d}")
        
        if not os.path.exists(surah_dir):
            QMessageBox.warning(self, "Dossier vide", f"Aucun segment trouvé pour la sourate {surah_num}.\nSegmentez d'abord.")
            return
        
        mp3_count = len(glob.glob(os.path.join(surah_dir, "*.mp3")))
        if mp3_count == 0:
            QMessageBox.warning(self, "Dossier vide", f"Aucun fichier MP3 dans {surah_dir}")
            return
        
        reply = QMessageBox.question(
            self,
            "Confirmer l'upload",
            f"Uploader la Sourate {surah_num} vers Hugging Face?\n\n"
            f"📁 {mp3_count} fichiers MP3 seront uploadés.\n\n"
            f"Cela peut prendre quelques minutes selon la connexion.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.progress_label.setText(f"⏳ Upload Sourate {surah_num} vers HF...")
            QApplication.processEvents()
            
            success = upload_surah_to_hf(surah_num, parent_widget=self)
            
            if success:
                self._completed_surahs.add(surah_num)
                self.progress_label.setText(f"✅ Sourate {surah_num} uploadée sur HF")
                QMessageBox.information(
                    self,
                    "Upload réussi",
                    f"✅ Sourate {surah_num} uploadée avec succès!\n\n"
                    f"Votre collègue la verra lors de son prochain démarrage."
                )
            else:
                self.progress_label.setText("❌ Échec de l'upload")
    
    def _open_admin_panel(self):
        """Ouvre le panneau d'administration pour vérifier/supprimer le travail du collègue."""
        dialog = AdminPanelDialog(self)
        dialog.exec()
    
    def _update_progress(self, percent: int, message: str, 
                         row: int = -1, op_progress: float = -1) -> None:
        """
        Met à jour la barre de progression principale et optionnellement celle d'un item.
        
        Args:
            percent: Pourcentage de progression (0-100)
            message: Message à afficher
            row: Index de la ligne pour la progression d'opération (-1 = ignorer)
            op_progress: Progression d'opération pour l'item (0.0-1.0, -1 = ignorer)
        """
        self.progress_bar.setValue(percent)
        self.progress_label.setText(message)
        
        if row >= 0 and op_progress >= 0:
            self.segment_delegate.set_operation_progress(row, op_progress)
            self.segments_list.viewport().update()
        
        QApplication.processEvents()
    
    def _wait_for_file_ready(self, file_path: str, max_wait: float = 5.0) -> bool:
        """
        Attend que le fichier soit complètement écrit et lisible.
        
        Args:
            file_path: Chemin du fichier à vérifier
            max_wait: Temps maximum d'attente en secondes
            
        Returns:
            True si le fichier est prêt, False si timeout
        """
        start_wait = time.time()
        while time.time() - start_wait < max_wait:
            if os.path.exists(file_path):
                try:
                    test_audio = AudioSegment.from_file(file_path)
                    if len(test_audio) > 0:
                        return True
                except:
                    pass
            time.sleep(0.1)
            QApplication.processEvents()
        return False
    
    def _setup_ui(self):
        """Construit l'interface utilisateur."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # --- Titre ---
        title = QLabel("Segmentation Audio du Coran")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # --- Sélection de fichier ---
        file_group = QGroupBox("Fichier Audio")
        file_layout = QHBoxLayout(file_group)
        
        self.file_label = QLabel("Aucun fichier sélectionné")
        self.file_label.setStyleSheet("color: gray; font-style: italic;")
        file_layout.addWidget(self.file_label, 1)
        
        self.browse_btn = QPushButton("📂 Parcourir...")
        self.browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.browse_btn)
        
        layout.addWidget(file_group)
        
        # --- Informations Sourate/Ayah ---
        quran_group = QGroupBox("Informations Coran")
        quran_layout = QHBoxLayout(quran_group)
        
        quran_layout.addWidget(QLabel("Sourate:"))
        self.surah_spin = QSpinBox()
        self.surah_spin.setRange(1, 114)
        self.surah_spin.setValue(1)
        self.surah_spin.valueChanged.connect(self._on_surah_changed)
        quran_layout.addWidget(self.surah_spin)
        
        quran_layout.addSpacing(20)
        
        quran_layout.addWidget(QLabel("Ayah de départ:"))
        self.start_ayah_spin = QSpinBox()
        self.start_ayah_spin.setRange(0, 286)
        self.start_ayah_spin.setValue(0)
        self.start_ayah_spin.setSpecialValueText("Basmala")
        self.start_ayah_spin.setToolTip("0 = Basmala, 1+ = Numéro d'ayat")
        quran_layout.addWidget(self.start_ayah_spin)
        
        quran_layout.addSpacing(20)
        
        quran_layout.addWidget(QLabel("Limite:"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 286)
        self.limit_spin.setValue(0)
        self.limit_spin.setSpecialValueText("Tous")
        self.limit_spin.setToolTip("0 = Tous les segments détectés")
        quran_layout.addWidget(self.limit_spin)
        
        quran_layout.addSpacing(30)
        
        # Bouton pour charger une sourate déjà traitée
        self.load_surah_btn = QPushButton("📂 Charger Sourate")
        self.load_surah_btn.setToolTip("Charger une sourate déjà segmentée depuis le dossier de sortie")
        self.load_surah_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.load_surah_btn.clicked.connect(self._load_existing_surah)
        quran_layout.addWidget(self.load_surah_btn)
        
        quran_layout.addStretch()
        
        # Affichage du total d'ayats
        self.total_ayats_label = QLabel("(7 ayats)")
        self.total_ayats_label.setStyleSheet("color: gray;")
        quran_layout.addWidget(self.total_ayats_label)
        
        layout.addWidget(quran_group)
        
        # --- Paramètres ---
        params_group = QGroupBox("Paramètres de détection")
        params_layout = QVBoxLayout(params_group)
        
        # Seuil de silence
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("Seuil de silence (dB):"))
        self.thresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.thresh_slider.setRange(Config.SILENCE_THRESH_MIN, Config.SILENCE_THRESH_MAX)
        self.thresh_slider.setValue(Config.DEFAULT_SILENCE_THRESH)
        self.thresh_slider.valueChanged.connect(self._update_thresh_label)
        thresh_layout.addWidget(self.thresh_slider)
        self.thresh_label = QLabel(f"{Config.DEFAULT_SILENCE_THRESH} dB")
        self.thresh_label.setMinimumWidth(60)
        thresh_layout.addWidget(self.thresh_label)
        params_layout.addLayout(thresh_layout)
        
        # Durée minimum de silence
        min_len_layout = QHBoxLayout()
        min_len_layout.addWidget(QLabel("Durée min. silence (ms):"))
        self.min_len_spin = QSpinBox()
        self.min_len_spin.setRange(Config.MIN_SILENCE_LEN_MIN, Config.MIN_SILENCE_LEN_MAX)
        self.min_len_spin.setValue(Config.DEFAULT_MIN_SILENCE_LEN)
        self.min_len_spin.setSingleStep(50)
        min_len_layout.addWidget(self.min_len_spin)
        min_len_layout.addStretch()
        params_layout.addLayout(min_len_layout)
        
        # Silence à conserver
        keep_layout = QHBoxLayout()
        keep_layout.addWidget(QLabel("Silence à conserver (ms):"))
        self.keep_spin = QSpinBox()
        self.keep_spin.setRange(Config.KEEP_SILENCE_MIN, Config.KEEP_SILENCE_MAX)
        self.keep_spin.setValue(Config.DEFAULT_KEEP_SILENCE)
        self.keep_spin.setSingleStep(50)
        keep_layout.addWidget(self.keep_spin)
        keep_layout.addStretch()
        params_layout.addLayout(keep_layout)
        
        # Mode Juz (multi-sourate)
        juz_layout = QHBoxLayout()
        self.juz_mode_checkbox = QCheckBox("📚 Mode Juz")
        self.juz_mode_checkbox.setToolTip(
            "Activez ce mode pour segmenter un fichier contenant plusieurs sourates.\n"
            "Les segments seront stockés dans 'juz_XX_temp/' puis vous pourrez\n"
            "utiliser '📤 Transférer' pour les déplacer vers leurs sourates."
        )
        self.juz_mode_checkbox.setStyleSheet("font-weight: bold; color: #8e44ad;")
        self.juz_mode_checkbox.toggled.connect(self._toggle_juz_mode)
        juz_layout.addWidget(self.juz_mode_checkbox)
        
        juz_layout.addWidget(QLabel("Numéro:"))
        self.juz_num_spin = QSpinBox()
        self.juz_num_spin.setRange(1, 30)
        self.juz_num_spin.setValue(30)
        self.juz_num_spin.setEnabled(False)
        self.juz_num_spin.setToolTip("Numéro du Juz (1-30) pour afficher les ayats correspondants")
        self.juz_num_spin.valueChanged.connect(self._on_juz_num_changed)
        juz_layout.addWidget(self.juz_num_spin)
        
        # Option pour ignorer l'Isti'adha (أَعُوذُ بِاللهِ)
        self.skip_istiadha_checkbox = QCheckBox("Ignorer Isti'adha")
        self.skip_istiadha_checkbox.setToolTip(
            "Cochez si le premier segment est 'أَعُوذُ بِاللهِ مِنَ الشَّيْطَانِ الرَّجِيمِ'\n"
            "(refuge contre Satan) et doit être ignoré dans la numérotation"
        )
        self.skip_istiadha_checkbox.setEnabled(True)  # Toujours disponible
        self.skip_istiadha_checkbox.toggled.connect(self._on_skip_istiadha_changed)
        juz_layout.addWidget(self.skip_istiadha_checkbox)
        
        juz_layout.addStretch()
        params_layout.addLayout(juz_layout)
        
        layout.addWidget(params_group)
        
        # --- Liste des segments + Prévisualisation ---
        segments_group = QGroupBox("Segments détectés")
        segments_main_layout = QVBoxLayout(segments_group)
        
        # Splitter horizontal: liste à gauche, preview à droite
        segments_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # -- Partie gauche: liste des segments --
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        
        self.segments_list = QListWidget()
        self.segments_list.setAlternatingRowColors(True)
        self.segments_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.segments_list.itemDoubleClicked.connect(self._play_selected_segment)
        self.segments_list.currentItemChanged.connect(self._on_segment_selected)
        
        # Delegate pour afficher les barres de progression
        self.segment_delegate = SegmentItemDelegate(self.segments_list)
        self.segments_list.setItemDelegate(self.segment_delegate)
        
        # Intercepter les clics sur l'icône play dans la liste (viewport pour les events de dessin)
        self.segments_list.viewport().installEventFilter(self)
        
        list_layout.addWidget(self.segments_list)
        
        segments_splitter.addWidget(list_widget)
        
        # -- Partie droite: prévisualisation de l'ayat --
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(5, 0, 0, 0)
        
        # Titre + option de verrouillage
        preview_header = QHBoxLayout()
        preview_title = QLabel("📖 Prévisualisation")
        preview_title.setStyleSheet("font-weight: bold; color: #333;")
        preview_header.addWidget(preview_title)
        
        preview_header.addStretch()
        
        self.lock_ayat_checkbox = QCheckBox("🔒 Verrouiller")
        self.lock_ayat_checkbox.setToolTip("Ne pas changer l'ayat quand le segment change\n(utile quand un ayat est sur plusieurs morceaux)")
        self.lock_ayat_checkbox.setStyleSheet("color: #666;")
        self.lock_ayat_checkbox.stateChanged.connect(self._on_lock_changed)
        preview_header.addWidget(self.lock_ayat_checkbox)
        
        self.bookmark_btn = QPushButton("⭐ Marquer")
        self.bookmark_btn.setToolTip("Marquer ce segment pour le retrouver facilement\n(utile pour le premier morceau d'un ayat sur plusieurs segments)")
        self.bookmark_btn.setStyleSheet("padding: 2px 8px; font-size: 12px;")
        self.bookmark_btn.setMaximumHeight(26)
        self.bookmark_btn.clicked.connect(self._toggle_bookmark)
        preview_header.addWidget(self.bookmark_btn)
        
        preview_layout.addLayout(preview_header)
        
        # Zone d'affichage de l'image de l'ayat (ScrollArea pour les grandes images)
        self.ayat_scroll = QScrollArea()
        self.ayat_scroll.setWidgetResizable(True)
        self.ayat_scroll.setMinimumSize(400, 250)
        self.ayat_scroll.setStyleSheet(
            "QScrollArea { background-color: #f5f5f5; border: 1px solid #ddd; border-radius: 5px; }"
        )
        
        self.ayat_image_label = QLabel()
        self.ayat_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ayat_image_label.setScaledContents(False)
        self.ayat_image_label.setWordWrap(True)
        self.ayat_image_label.setStyleSheet("padding: 10px;")
        self.ayat_image_label.setText("Sélectionnez un segment\npour voir l'ayat")
        
        self.ayat_scroll.setWidget(self.ayat_image_label)
        preview_layout.addWidget(self.ayat_scroll, 1)
        
        segments_splitter.addWidget(preview_widget)
        
        # Proportions du splitter (plus de place pour la preview)
        segments_splitter.setSizes([350, 450])
        segments_main_layout.addWidget(segments_splitter)
        
        # Contrôles de lecture
        playback_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("▶️ Lecture")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._play_selected_segment)
        playback_layout.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_playback)
        playback_layout.addWidget(self.stop_btn)
        
        playback_layout.addSpacing(10)
        
        self.auto_play_checkbox = QCheckBox("🔄 Auto")
        self.auto_play_checkbox.setToolTip("Lecture automatique: joue tous les ayats l'un après l'autre (500ms entre chaque)")
        self.auto_play_checkbox.setStyleSheet("font-weight: bold; color: #00aa00;")
        self.auto_play_checkbox.setChecked(True)
        self.auto_play_checkbox.toggled.connect(self._toggle_auto_play)
        playback_layout.addWidget(self.auto_play_checkbox)
        
        playback_layout.addSpacing(15)
        
        self.merge_btn = QPushButton("🔗 Fusionner")
        self.merge_btn.setEnabled(False)
        self.merge_btn.setToolTip("Sélectionnez 2+ segments consécutifs pour les fusionner")
        self.merge_btn.clicked.connect(self._merge_selected_segments)
        playback_layout.addWidget(self.merge_btn)
        
        self.undo_merge_btn = QPushButton("↩️ Annuler fusion")
        self.undo_merge_btn.setEnabled(False)
        self.undo_merge_btn.setToolTip("Annuler la dernière fusion")
        self.undo_merge_btn.clicked.connect(self._undo_merge)
        playback_layout.addWidget(self.undo_merge_btn)
        
        playback_layout.addSpacing(10)
        
        self.split_btn = QPushButton("✂️ Diviser")
        self.split_btn.setEnabled(False)
        self.split_btn.setToolTip("Diviser un segment en 2 parties (si 2 ayats dans un morceau)")
        self.split_btn.clicked.connect(self._split_segment)
        playback_layout.addWidget(self.split_btn)
        
        self.undo_split_btn = QPushButton("↩️ Annuler division")
        self.undo_split_btn.setEnabled(False)
        self.undo_split_btn.setToolTip("Annuler la dernière division")
        self.undo_split_btn.clicked.connect(self._undo_split)
        playback_layout.addWidget(self.undo_split_btn)
        
        playback_layout.addSpacing(10)
        
        self.validate_btn = QPushButton("✅ Valider Sourate")
        self.validate_btn.setToolTip("Nettoyer le cache et les backups (opération irréversible)")
        self.validate_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self.validate_btn.clicked.connect(self._validate_surah)
        playback_layout.addWidget(self.validate_btn)
        
        playback_layout.addSpacing(10)
        
        self.delete_btn = QPushButton("🗑️ Supprimer")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setToolTip("Supprimer le segment sélectionné")
        self.delete_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        self.delete_btn.clicked.connect(self._delete_segment)
        playback_layout.addWidget(self.delete_btn)
        
        self.insert_btn = QPushButton("➕ Insérer")
        self.insert_btn.setEnabled(False)
        self.insert_btn.setToolTip("Insérer un segment manquant à cette position")
        self.insert_btn.setStyleSheet("background-color: #3498db; color: white;")
        self.insert_btn.clicked.connect(self._insert_missing_segment)
        playback_layout.addWidget(self.insert_btn)
        
        playback_layout.addSpacing(10)
        
        self.new_surah_btn = QPushButton("📖 Nouvelle Sourate")
        self.new_surah_btn.setEnabled(False)
        self.new_surah_btn.setToolTip("Marquer ce segment comme début d'une nouvelle sourate (Basmala)")
        self.new_surah_btn.setStyleSheet("background-color: #8e44ad; color: white;")
        self.new_surah_btn.clicked.connect(self._mark_new_surah)
        playback_layout.addWidget(self.new_surah_btn)
        
        self.undo_transfer_btn = QPushButton("↩️ Annuler transfert")
        self.undo_transfer_btn.setEnabled(False)
        self.undo_transfer_btn.setToolTip("Annuler le dernier transfert de sourate")
        self.undo_transfer_btn.clicked.connect(self._undo_transfer)
        playback_layout.addWidget(self.undo_transfer_btn)
        
        self.playback_label = QLabel("Sélectionnez un segment")
        self.playback_label.setStyleSheet("color: gray; font-style: italic;")
        playback_layout.addWidget(self.playback_label, 1)
        
        segments_main_layout.addLayout(playback_layout)
        
        layout.addWidget(segments_group, 1)
        
        # --- Progression ---
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("Prêt")
        self.progress_label.setMinimumWidth(200)
        progress_layout.addWidget(self.progress_label)
        
        # Chronomètre
        self.elapsed_label = QLabel("⏱️ 00:00")
        self.elapsed_label.setMinimumWidth(80)
        self.elapsed_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #0066cc;")
        progress_layout.addWidget(self.elapsed_label)
        
        layout.addLayout(progress_layout)
        
        # --- Boutons d'action ---
        btn_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("▶️ Démarrer")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start_processing)
        self.start_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.start_btn)
        
        self.cancel_btn = QPushButton("⏹️ Annuler")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_processing)
        self.cancel_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.cancel_btn)
        
        self.open_output_btn = QPushButton("📁 Ouvrir dossier")
        self.open_output_btn.clicked.connect(self._open_output_folder)
        self.open_output_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.open_output_btn)
        
        self.verify_btn = QPushButton("🔍 Vérifier")
        self.verify_btn.setEnabled(False)
        self.verify_btn.setToolTip("Vérifie les segments contre le texte du Quran")
        self.verify_btn.clicked.connect(self._verify_segments)
        self.verify_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.verify_btn)
        
        self.view_log_btn = QPushButton("📋 Log")
        self.view_log_btn.setToolTip("Voir le journal des actions (fusion, division, etc.)")
        self.view_log_btn.clicked.connect(self._view_action_log)
        self.view_log_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.view_log_btn)
        
        self.upload_surah_btn = QPushButton("📤 Upload HF")
        self.upload_surah_btn.setToolTip("Uploader la sourate actuelle vers Hugging Face")
        self.upload_surah_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        self.upload_surah_btn.clicked.connect(self._upload_current_surah)
        self.upload_surah_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.upload_surah_btn)
        
        self.admin_btn = QPushButton("🔧 Admin")
        self.admin_btn.setToolTip("Vérifier / supprimer le travail du collègue")
        self.admin_btn.setStyleSheet("background-color: #607D8B; color: white; font-weight: bold;")
        self.admin_btn.clicked.connect(self._open_admin_panel)
        self.admin_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.admin_btn)
        
        layout.addLayout(btn_layout)
    
    def _update_thresh_label(self, value):
        """Met à jour l'affichage du seuil de silence."""
        self.thresh_label.setText(f"{value} dB")
    
    def _on_surah_changed(self, value):
        """Met à jour le max de l'ayah et affiche le total."""
        total = Config.SURAH_AYAT_COUNT.get(value, 7)
        self.start_ayah_spin.setRange(0, total)  # 0 = Basmala
        self.total_ayats_label.setText(f"({total} ayats)")
    
    def _browse_file(self):
        """Ouvre le dialogue de sélection de fichier."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un fichier audio",
            Config.AUDIO_INPUT_DIR,
            "Fichiers Audio (*.mp3 *.wav *.m4a *.ogg *.flac);;Tous (*.*)"
        )
        
        if file_path:
            self.current_file = file_path
            self.file_label.setText(Path(file_path).name)
            self.file_label.setStyleSheet("color: black; font-style: normal;")
            self.start_btn.setEnabled(True)
            self.segments_list.clear()
            self.progress_bar.setValue(0)
            self.progress_label.setText("Prêt")
    
    def _load_existing_surah(self):
        """Charge une sourate déjà segmentée depuis le dossier de sortie."""
        surah_num = self.surah_spin.value()
        
        # Mode Juz: charger depuis juz_XX_temp
        if self.juz_mode:
            juz_temp_name = f"juz_{self.juz_num:02d}_temp"
            surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, juz_temp_name)
            folder_label = juz_temp_name
        else:
            surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{surah_num:03d}")
            folder_label = f"Sourate {surah_num}"
        
        if not os.path.exists(surah_dir):
            if self.juz_mode:
                QMessageBox.warning(
                    self,
                    "Dossier non trouvé",
                    f"Aucun dossier '{juz_temp_name}' trouvé.\n\n"
                    f"Chemin: {surah_dir}\n\n"
                    "Segmentez d'abord un fichier Juz."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Dossier non trouvé",
                    f"Aucun dossier trouvé pour la sourate {surah_num}.\n\n"
                    f"Chemin: {surah_dir}\n\n"
                    "Segmentez d'abord cette sourate."
                )
            return
        
        # Lister les fichiers MP3 dans le dossier
        mp3_files = sorted(glob.glob(os.path.join(surah_dir, "*.mp3")))
        
        if not mp3_files:
            QMessageBox.warning(
                self,
                "Aucun segment",
                f"Aucun fichier MP3 trouvé dans:\n{surah_dir}"
            )
            return
        
        # Vider la liste et charger les segments
        self.segments_list.clear()
        
        for file_path in mp3_files:
            file_name = os.path.basename(file_path)
            ayah_str = file_name.replace(".mp3", "")
            
            try:
                segment_num = int(ayah_str)
            except:
                continue
            
            # Obtenir la durée du fichier audio
            try:
                if PYDUB_AVAILABLE:
                    audio = AudioSegment.from_file(file_path)
                    duration_ms = len(audio)
                    duration_sec = duration_ms / 1000
                else:
                    duration_sec = 0
            except:
                duration_sec = 0
            
            # Créer l'item selon le mode
            if self.juz_mode:
                # Mode Juz: numérotation simple
                item = QListWidgetItem(f"📚 Segment {segment_num:03d} | {duration_sec:.1f}s")
            else:
                # Mode normal: numérotation par ayah
                # Prendre en compte skip_istiadha et Sourate 9 (pas de Basmala)
                row_position = self.segments_list.count()  # Position actuelle (0-indexed)
                
                if self.skip_istiadha and row_position == 0:
                    # Premier segment = Isti'adha
                    ayah_display = "Isti'adha"
                elif surah_num == 1:
                    # Sourate 1 (Al-Fatiha): Basmala = Ayat 1 (pas ayat 0)
                    if self.skip_istiadha:
                        ayah_num = row_position  # Isti'adha=0, A001=1, A002=2...
                    else:
                        ayah_num = row_position + 1  # A001=0, A002=1...
                    ayah_display = f"A{ayah_num:03d}"
                elif surah_num == 9:
                    # Sourate 9 (Tawba) n'a pas de Basmala
                    if self.skip_istiadha:
                        ayah_num = row_position  # Isti'adha=0, A001=1, A002=2...
                    else:
                        ayah_num = row_position + 1  # A001=0, A002=1...
                    ayah_display = f"A{ayah_num:03d}"
                else:
                    # Autres sourates (2-8, 10-114) avec Basmala séparée
                    if self.skip_istiadha:
                        ayah_num = row_position - 1  # Isti'adha=0, Basmala=1, A001=2...
                    else:
                        ayah_num = row_position  # Basmala=0, A001=1...
                    
                    if ayah_num == 0:
                        ayah_display = "Basmala"
                    else:
                        ayah_display = f"A{ayah_num:03d}"
                
                item = QListWidgetItem(f"S{surah_num:03d}:{ayah_display} | {duration_sec:.1f}s")
            
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            self.segments_list.addItem(item)
        
        # Activer les boutons
        self.play_btn.setEnabled(True)
        self.merge_btn.setEnabled(True)
        self.split_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.insert_btn.setEnabled(True)
        self.new_surah_btn.setEnabled(True)
        self.verify_btn.setEnabled(True)
        
        # Mettre à jour l'interface
        nb_segments = self.segments_list.count()
        self.progress_bar.setValue(100)
        self.progress_label.setText(f"✅ {nb_segments} segments chargés")
        
        if self.juz_mode:
            self.playback_label.setText("📚 Juz chargé - Écoutez et marquez les sourates")
            self.playback_label.setStyleSheet("color: #8e44ad; font-weight: bold;")
            self.file_label.setText(f"📂 {juz_temp_name} (chargé)")
            self.file_label.setStyleSheet("color: #8e44ad; font-weight: bold;")
        else:
            self.playback_label.setText("Sourate chargée - Double-cliquez pour lire")
            self.playback_label.setStyleSheet("color: blue;")
            self.file_label.setText(f"📂 Sourate {surah_num} (chargée)")
            self.file_label.setStyleSheet("color: blue; font-weight: bold;")
        
        if self.juz_mode:
            QMessageBox.information(
                self,
                "📚 Juz chargé",
                f"✅ {nb_segments} segments chargés depuis {juz_temp_name}!\n\n"
                f"Utilisez:\n"
                f"• 🔄 Auto + ▶️ Lecture pour écouter en continu\n"
                f"• 📖 Nouvelle Sourate pour marquer les Basmalas\n"
                f"• 📤 Transférer pour déplacer vers les sourates"
            )
        else:
            QMessageBox.information(
                self,
                "Chargement terminé",
                f"✅ {nb_segments} segments chargés pour la sourate {surah_num}!"
            )
    
    def _start_processing(self):
        """Démarre le traitement audio."""
        if not self.current_file:
            return
        
        if not PYDUB_AVAILABLE:
            QMessageBox.critical(
                self,
                "Erreur",
                "Le module 'pydub' n'est pas installé.\n\n"
                "Installez-le avec: pip install pydub\n"
                "Et installez ffmpeg sur votre système."
            )
            return
        
        # Vérifier si la sourate est déjà marquée comme terminée (HF ou local)
        surah_num = self.surah_spin.value()
        if hasattr(self, '_completed_surahs') and surah_num in self._completed_surahs:
            QMessageBox.warning(
                self,
                "🚫 Sourate déjà traitée",
                f"La Sourate {surah_num} est déjà traitée (HF ou localement).\n\n"
                f"💡 Utilisez le panneau Admin (🔧) pour la supprimer si besoin,\n"
                f"   ou sélectionnez une autre sourate à segmenter."
            )
            return
        
        # Vérifier si la sourate a déjà été segmentée localement
        surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{surah_num:03d}")
        
        if os.path.exists(surah_dir):
            existing_mp3s = glob.glob(os.path.join(surah_dir, "*.mp3"))
            if existing_mp3s:
                reply = QMessageBox.warning(
                    self,
                    "⚠️ Sourate déjà segmentée",
                    f"La sourate {surah_num} contient déjà {len(existing_mp3s)} segments!\n\n"
                    f"📂 {surah_dir}\n\n"
                    f"Voulez-vous vraiment ÉCRASER les fichiers existants?\n\n"
                    f"💡 Conseil: Utilisez '📂 Charger Sourate' pour charger les segments existants,\n"
                    f"    ou '▶️ Lecture' pour lire un segment sélectionné.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No  # Par défaut = Non
                )
                if reply == QMessageBox.StandardButton.No:
                    return
        
        # Vérifier la taille du fichier et avertir si gros
        file_size_mb = os.path.getsize(self.current_file) / (1024 * 1024)
        if file_size_mb > 50:  # Plus de 50 MB
            reply = QMessageBox.question(
                self,
                "Fichier volumineux",
                f"⚠️ Fichier de {file_size_mb:.0f} MB détecté.\n\n"
                f"L'analyse des silences peut prendre 1-3 minutes.\n"
                f"L'application peut sembler figée mais elle travaille.\n\n"
                f"Continuer?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Vider la liste
        self.segments_list.clear()
        
        # Créer et démarrer le worker
        self.worker = AudioSplitterWorker(
            audio_path=self.current_file,
            output_dir=Config.AUDIO_OUTPUT_DIR,
            surah_num=self.surah_spin.value(),
            start_ayah=self.start_ayah_spin.value(),
            limit=self.limit_spin.value(),
            silence_thresh=self.thresh_slider.value(),
            min_silence_len=self.min_len_spin.value(),
            keep_silence=self.keep_spin.value(),
            juz_mode=self.juz_mode,
            juz_num=self.juz_num
        )
        
        # Connecter les signaux
        self.worker.progress.connect(self._on_progress)
        self.worker.segment_found.connect(self._on_segment_found)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.cancelled.connect(self._on_cancelled)
        
        # Mettre à jour l'interface
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.browse_btn.setEnabled(False)
        
        # Démarrer le chronomètre
        self.start_time = time.time()
        self.elapsed_label.setText("⏱️ 00:00")
        self.elapsed_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #ff6600;")
        self.elapsed_timer.start(1000)
        
        # Démarrer
        self.worker.start()
    
    def _cancel_processing(self):
        """Annule le traitement en cours."""
        if self.worker:
            self.worker.cancel()
            self.progress_label.setText("⏳ Annulation en cours...")
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("⏳ Annulation...")
    
    def _on_cancelled(self):
        """Callback quand le traitement est annulé."""
        # Arrêter le chronomètre
        self.elapsed_timer.stop()
        self.elapsed_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #ff9900;")
        
        # Réinitialiser l'interface
        self.progress_bar.setValue(0)
        self.progress_label.setText("❌ Traitement annulé")
        
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("⏹️ Annuler")
        self.browse_btn.setEnabled(True)
        
        self.playback_label.setText("Traitement annulé")
        self.playback_label.setStyleSheet("color: orange;")
    
    def _update_elapsed_time(self):
        """Met à jour le chronomètre."""
        if self.start_time:
            elapsed = int(time.time() - self.start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60
            self.elapsed_label.setText(f"⏱️ {minutes:02d}:{seconds:02d}")
    
    def _on_progress(self, percent, message):
        """Callback de progression."""
        self.progress_bar.setValue(percent)
        self.progress_label.setText(message)
    
    def _on_segment_found(self, surah, ayah, start_ms, end_ms):
        """Callback quand un segment est détecté."""
        duration = (end_ms - start_ms) / 1000
        start_sec = start_ms / 1000
        
        if self.juz_mode:
            # Mode Juz: numérotation simple (001, 002, ...)
            segment_num = self.segments_list.count() + 1
            file_name = f"{segment_num:03d}.mp3"
            item = QListWidgetItem(f"📚 Segment {segment_num:03d} | {start_sec:.1f}s → {duration:.1f}s")
            juz_temp_dir = f"juz_{self.juz_num:02d}_temp"
            file_path = os.path.join(Config.AUDIO_OUTPUT_DIR, juz_temp_dir, file_name)
        else:
            # Mode normal: numérotation par ayah
            if ayah == 0:
                ayah_display = "Basmala"
                file_name = "000.mp3"
            else:
                ayah_display = f"A{ayah:03d}"
                file_name = f"{ayah:03d}.mp3"
            
            item = QListWidgetItem(f"S{surah:03d}:{ayah_display} | {start_sec:.1f}s → {duration:.1f}s")
            file_path = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{surah:03d}", file_name)
        
        # Créer l'item avec le chemin du fichier en data
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        self.segments_list.addItem(item)
    
    def _on_finished(self, nb_segments, output_dir):
        """Callback de fin de traitement."""
        # Arrêter le chronomètre
        self.elapsed_timer.stop()
        total_time = int(time.time() - self.start_time) if self.start_time else 0
        minutes = total_time // 60
        seconds = total_time % 60
        self.elapsed_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #00aa00;")
        
        self.progress_bar.setValue(100)
        self.progress_label.setText(f"✅ {nb_segments} segments en {minutes}m{seconds}s")
        
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.browse_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.merge_btn.setEnabled(True)
        self.split_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.insert_btn.setEnabled(True)
        self.new_surah_btn.setEnabled(True)
        self.verify_btn.setEnabled(True)
        self.playback_label.setText("Double-cliquez pour lire, Ctrl+clic pour fusionner")
        self.playback_label.setStyleSheet("color: green;")
        
        if self.juz_mode:
            # Mode Juz: afficher le dossier temporaire et activer le transfert
            juz_temp_dir = os.path.join(output_dir, f"juz_{self.juz_num:02d}_temp")
            
            QMessageBox.information(
                self,
                "📚 Segmentation Juz terminée",
                f"✅ {nb_segments} segments créés en {minutes}m{seconds}s!\n\n"
                f"📂 Dossier temporaire:\n   {juz_temp_dir}\n\n"
                f"📋 Prochaines étapes:\n"
                f"   1. Vérifiez les segments (lecture, fusion si nécessaire)\n"
                f"   2. Utilisez '📖 Nouvelle Sourate' pour transférer chaque sourate\n"
                f"   3. Pour la dernière sourate: sélectionnez le 1er segment"
            )
        else:
            # Mode normal: afficher le dossier de la sourate
            surah_folder = os.path.join(output_dir, f"{self.surah_spin.value():03d}")
            QMessageBox.information(
                self,
                "Terminé",
                f"✅ {nb_segments} ayats créés en {minutes}m{seconds}s!\n\n"
                f"Sourate {self.surah_spin.value()}\n"
                f"Dossier: {surah_folder}"
            )
    
    def _on_error(self, message):
        """Callback d'erreur."""
        # Arrêter le chronomètre
        self.elapsed_timer.stop()
        self.elapsed_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #cc0000;")
        
        self.progress_bar.setValue(0)
        self.progress_label.setText("❌ Erreur")
        
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.browse_btn.setEnabled(True)
        
        QMessageBox.critical(self, "Erreur", message)
    
    def _open_output_folder(self):
        """Ouvre le dossier de sortie dans l'explorateur."""
        output_path = os.path.abspath(Config.AUDIO_OUTPUT_DIR)
        os.makedirs(output_path, exist_ok=True)
        
        if sys.platform == "darwin":
            subprocess.run(["open", output_path])
        elif sys.platform == "win32":
            subprocess.run(["explorer", output_path])
        else:
            subprocess.run(["xdg-open", output_path])
    
    def _view_action_log(self):
        """Ouvre le fichier de log des actions."""
        log_path = os.path.abspath(Config.ACTION_LOG_FILE)
        
        if not os.path.exists(log_path):
            QMessageBox.information(
                self, "Log vide",
                "Aucune action n'a encore été enregistrée.\n\n"
                "Le log sera créé lors de la première opération\n"
                "(fusion, division, suppression, etc.)"
            )
            return
        
        # Ouvrir le fichier avec l'application par défaut
        if sys.platform == "darwin":
            subprocess.run(["open", log_path])
        elif sys.platform == "win32":
            subprocess.run(["notepad", log_path])
        else:
            subprocess.run(["xdg-open", log_path])
    
    def _set_marquee_text(self, text: str):
        """Désactivé - le texte défilant a été supprimé."""
        pass
    
    def _update_marquee(self):
        """Désactivé - le texte défilant a été supprimé."""
        pass
    
    def _on_lock_changed(self, state):
        """Quand le verrouillage est activé/désactivé, bascule le mode multi-sélection."""
        if state == Qt.CheckState.Checked.value:
            # Mode multi-sélection activé (pour fusion des segments d'un même ayat)
            self.playback_multi_select_mode = True
            
            # Verrouillage activé → marquer automatiquement
            item = self.segments_list.currentItem()
            if item:
                row = self.segments_list.row(item)
                if row not in self.bookmarked_rows:
                    self._toggle_bookmark()
                
                # Activer l'auto-play s'il ne l'est pas déjà
                if not self.auto_play_enabled:
                    self.auto_play_checkbox.setChecked(True)
                
                # Lancer la lecture du segment courant uniquement s'il n'est pas déjà en cours
                if not (self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                        and self.playing_row == row):
                    self._play_selected_segment(item)
        else:
            # Mode normal (pas de multi-sélection)
            self.playback_multi_select_mode = False
    
    def _toggle_bookmark(self):
        """Marque ou démarque le segment sélectionné avec une étoile."""
        item = self.segments_list.currentItem()
        if not item:
            return
        
        row = self.segments_list.row(item)
        text = item.text()
        
        if row in self.bookmarked_rows:
            # Démarquer
            self.bookmarked_rows.discard(row)
            if text.startswith("⭐ "):
                item.setText(text[3:])
            self.bookmark_btn.setText("⭐ Marquer")
            self.bookmark_btn.setStyleSheet("padding: 2px 8px; font-size: 12px;")
        else:
            # Marquer
            self.bookmarked_rows.add(row)
            if not text.startswith("⭐ "):
                item.setText("⭐ " + text)
            self.bookmark_btn.setText("❌ Démarquer")
            self.bookmark_btn.setStyleSheet(
                "padding: 2px 8px; font-size: 12px; background-color: #ffeb3b;"
            )
        
        # Logger
        action_logger.log_state_snapshot(
            f"BOOKMARK {'AJOUTÉ' if row in self.bookmarked_rows else 'RETIRÉ'} - Segment {row}",
            self.segments_list.count(),
            get_segment_files(self._get_output_dir())
        )
    
    def _update_bookmark_button(self, row: int):
        """Met à jour le texte du bouton selon l'état du bookmark du segment."""
        if row in self.bookmarked_rows:
            self.bookmark_btn.setText("❌ Démarquer")
            self.bookmark_btn.setStyleSheet(
                "padding: 2px 8px; font-size: 12px; background-color: #ffeb3b;"
            )
        else:
            self.bookmark_btn.setText("⭐ Marquer")
            self.bookmark_btn.setStyleSheet("padding: 2px 8px; font-size: 12px;")
    
    def _on_segment_selected(self, current, previous):
        """Callback quand un segment est sélectionné - affiche l'image de l'ayat."""
        if not current:
            self.ayat_image_label.setText("Sélectionnez un segment\npour voir l'ayat")
            self._set_marquee_text("")
            return
        
        # Mettre à jour le bouton de bookmark
        self._update_bookmark_button(self.segments_list.row(current))
        
        # Si le verrouillage est activé, ne pas changer l'affichage
        if self.lock_ayat_checkbox.isChecked():
            return
        
        # Extraire le numéro de sourate et ayat du texte
        text = current.text()
        is_merged = False
        merged_range = ""
        
        # Mode Juz: format "📚 Segment 001 | ..."
        if text.startswith("📚"):
            # IMPORTANT: Utiliser la position dans la liste (row) et non le numéro du segment
            # Car après une fusion, le numéro dans le texte ne correspond plus à la position réelle
            row_idx = self.segments_list.row(current)
            
            segment_num_str = text.split(" | ")[0].replace("📚 Segment ", "").strip()
            try:
                segment_num = int(segment_num_str)
            except:
                segment_num = row_idx + 1
            
            # Gérer l'option Isti'adha (décalage de 1)
            if self.skip_istiadha:
                if row_idx == 0:
                    # Premier segment = Isti'adha, afficher message spécial
                    self.ayat_image_label.setText(
                        f"🕌 Isti'adha\n\n"
                        f"أَعُوذُ بِاللهِ مِنَ\n"
                        f"الشَّيْطَانِ الرَّجِيمِ\n\n"
                        f"(Segment ignoré dans\n"
                        f"la numérotation)"
                    )
                    self._set_marquee_text("💡 Ce segment contient la demande de refuge contre Satan")
                    return
                else:
                    # Décaler l'index de 1 (row 1 → index 0)
                    segment_idx = row_idx - 1
            else:
                segment_idx = row_idx  # Utiliser directement la position dans la liste
            
            # Vérifier si on a la liste des ayats du Juz
            if self.juz_ayat_list and 0 <= segment_idx < len(self.juz_ayat_list):
                surah, ayah = self.juz_ayat_list[segment_idx]
                
                # Afficher l'image de l'ayat correspondant
                self.ayat_image_label.setText("⏳ Chargement...")
                QApplication.processEvents()
                
                # Construire l'index si nécessaire
                if self.ayat_index is None:
                    self.ayat_index = build_ayat_index()
                
                pixmap = get_cached_ayat_image(surah, ayah)
                
                if pixmap and not pixmap.isNull():
                    # Afficher l'image à une taille lisible (max 600px de large)
                    max_width = 600
                    if pixmap.width() > max_width:
                        scaled = pixmap.scaledToWidth(
                            max_width,
                            Qt.TransformationMode.SmoothTransformation
                        )
                    else:
                        scaled = pixmap
                    self.ayat_image_label.setPixmap(scaled)
                    
                    # Afficher les infos
                    quran_df = load_quran_text()
                    if ayah == 0:
                        ayat_text = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
                        ayat_label = "Basmala"
                    else:
                        ayat_text = get_ayat_text(quran_df, surah, ayah) if quran_df is not None else ""
                        ayat_label = f"Ayat {ayah}"
                    
                    # Afficher la position et l'ayat correspondant
                    position_info = f"[Position {row_idx + 1}/{self.segments_list.count()}]"
                    self._set_marquee_text(
                        f"📚 Juz {self.juz_num} | Sourate {surah}, {ayat_label} {position_info} • {ayat_text}"
                    )
                else:
                    ayat_display = "Basmala" if ayah == 0 else f"A{ayah}"
                    self.ayat_image_label.setText(f"❌ Image non disponible\nS{surah}:{ayat_display}")
                    self._set_marquee_text(f"Juz {self.juz_num}, Segment #{segment_num_str}")
            else:
                # Pas de liste ou segment hors limites
                total_segments = self.segments_list.count()
                expected_ayats = len(self.juz_ayat_list)
                
                if total_segments != expected_ayats:
                    warning = f"⚠️ {total_segments} segments ≠ {expected_ayats} ayats\n(fusion a changé la correspondance)"
                else:
                    warning = f"⚠️ Position hors limites\n({expected_ayats} ayats dans ce Juz)"
                
                self.ayat_image_label.setText(
                    f"📚 Juz {self.juz_num}\n\n"
                    f"Position: {row_idx + 1}\n"
                    f"Index ayat: {segment_idx}\n\n"
                    f"{warning}"
                )
                self._set_marquee_text("💡 Après fusion, la correspondance peut être décalée")
            return
        
        try:
            # Format: "S067:Basmala | ..." ou "S067:A001 | ..." ou "S067:Isti'adha | ..."
            main_part = text.split(" | ")[0]
            
            # Gérer le format fusionné (prendre le premier ayat)
            if "→" in main_part:
                is_merged = True
                merged_range = main_part
                main_part = main_part.split("→")[0]
            
            surah_part, ayah_part = main_part.split(":")
            surah = int(surah_part.replace("S", ""))
            
            # Gérer Isti'adha
            if ayah_part == "Isti'adha":
                self.ayat_image_label.setText(
                    f"🕌 Isti'adha\n\n"
                    f"أَعُوذُ بِاللهِ مِنَ\n"
                    f"الشَّيْطَانِ الرَّجِيمِ\n\n"
                    f"(Segment ignoré dans\n"
                    f"la numérotation)"
                )
                self._set_marquee_text("💡 Ce segment contient la demande de refuge contre Satan")
                return
            elif ayah_part == "Basmala":
                ayah = 0
            else:
                ayah = int(ayah_part.replace("A", ""))
        except:
            self.ayat_image_label.setText("Format invalide")
            return
        
        # Construire l'index si nécessaire
        if self.ayat_index is None:
            self.ayat_image_label.setText("⏳ Chargement de l'index...")
            QApplication.processEvents()
            self.ayat_index = build_ayat_index()
        
        # Récupérer l'image de l'ayat
        self.ayat_image_label.setText("⏳ Chargement de l'image...")
        QApplication.processEvents()
        
        pixmap = get_cached_ayat_image(surah, ayah)
        
        if pixmap and not pixmap.isNull():
            # Afficher l'image à une taille lisible (max 600px de large)
            max_width = 600
            if pixmap.width() > max_width:
                scaled = pixmap.scaledToWidth(
                    max_width,
                    Qt.TransformationMode.SmoothTransformation
                )
            else:
                scaled = pixmap
            self.ayat_image_label.setPixmap(scaled)
            
            # Afficher les infos
            quran_df = load_quran_text()
            
            if ayah == 0:
                ayat_text = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
                ayat_label = "Basmala"
            else:
                ayat_text = get_ayat_text(quran_df, surah, ayah) if quran_df is not None else ""
                ayat_label = f"Ayat {ayah}"
            
            # Ajouter info fusion si applicable
            if is_merged:
                ayat_label += f" 🔗 (fusionné: {merged_range})"
            
            self._set_marquee_text(f"Sourate {surah}, {ayat_label} • {ayat_text}")
        else:
            ayat_display = "Basmala" if ayah == 0 else f"A{ayah}"
            self.ayat_image_label.setText(f"❌ Image non disponible\npour S{surah}:{ayat_display}")
            self._set_marquee_text("Vérifiez que l'annotation existe")
    
    def _play_selected_segment(self, item=None):
        """Joue le segment sélectionné."""
        if item is None:
            item = self.segments_list.currentItem()
        
        if not item:
            return
        
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path or not os.path.exists(file_path):
            self.playback_label.setText("❌ Fichier non trouvé")
            self.playback_label.setStyleSheet("color: red;")
            return
        
        # Sélectionner le segment dans la liste pour faciliter la fusion ensuite
        self.segments_list.setCurrentItem(item)
        if not self.playback_multi_select_mode:
            # Mode normal : effacer la sélection précédente
            self.segments_list.clearSelection()
        item.setSelected(True)
        
        # Si lecture manuelle sans verrouillage, désactiver le mode multi-sélection
        if not self.lock_ayat_checkbox.isChecked():
            self.playback_multi_select_mode = False
        
        # Arrêter la lecture en cours si nécessaire
        self.media_player.stop()
        
        # Charger et lire le fichier
        self.media_player.setSource(QUrl.fromLocalFile(os.path.abspath(file_path)))
        self.media_player.play()
        
        # Mettre à jour l'affichage
        ayah_name = item.text().split(" | ")[0]
        self.playback_label.setText(f"🔊 Lecture: {ayah_name}")
        self.playback_label.setStyleSheet("color: blue; font-weight: bold;")
        self.stop_btn.setEnabled(True)
    
    def _stop_playback(self):
        """Arrête la lecture en cours."""
        self.media_player.stop()
        self.auto_play_timer.stop()  # Arrêter le timer auto-play si actif
        self.playback_label.setText("⏹️ Arrêté")
        self.playback_label.setStyleSheet("color: gray;")
        self.stop_btn.setEnabled(False)
    
    def _on_playback_state_changed(self, state):
        """Callback quand l'état de lecture change."""
        if state == QMediaPlayer.PlaybackState.StoppedState:
            if self.segments_list.count() > 0:
                if self.auto_play_enabled:
                    self.playback_label.setText("🔄 Mode auto actif")
                else:
                    self.playback_label.setText("Sélectionnez un segment")
                self.playback_label.setStyleSheet("color: green;")
            self.stop_btn.setEnabled(False)
            # Effacer la barre de progression
            if self.playing_row >= 0:
                self.segment_delegate.set_playback_progress(self.playing_row, 0)
                self.segments_list.viewport().update()
                self.playing_row = -1
            # Si lecture auto post-fusion, désélectionner
            if self.auto_deselect_after_play:
                self.segments_list.clearSelection()
                self.auto_deselect_after_play = False
        elif state == QMediaPlayer.PlaybackState.PlayingState:
            self.stop_btn.setEnabled(True)
            # Enregistrer la ligne en cours de lecture
            self.playing_row = self.segments_list.currentRow()
            # Remonter le panneau de prévisualisation au début de l'ayat (sauf si verrouillé)
            if not self.lock_ayat_checkbox.isChecked():
                v_scrollbar = self.ayat_scroll.verticalScrollBar()
                if v_scrollbar:
                    v_scrollbar.setValue(0)
    
    def _on_playback_position_changed(self, position):
        """Callback quand la position de lecture change."""
        if self.playing_row >= 0 and self.playing_duration > 0:
            progress = position / self.playing_duration
            self.segment_delegate.set_playback_progress(self.playing_row, progress)
            self.segments_list.viewport().update()
            
            # Défilement automatique du panneau de prévisualisation (même si verrouillé)
            v_scrollbar = self.ayat_scroll.verticalScrollBar()
            if v_scrollbar and v_scrollbar.maximum() > 0:
                # Vitesse configurable (voir self.SCROLL_SPEED_FACTOR dans __init__)
                scroll_value = int(progress * v_scrollbar.maximum() * self.SCROLL_SPEED_FACTOR)
                scroll_value = min(scroll_value, v_scrollbar.maximum())
                v_scrollbar.setValue(scroll_value)
    
    def _on_playback_duration_changed(self, duration):
        """Callback quand la durée du média est connue."""
        self.playing_duration = duration
    
    def eventFilter(self, obj, event):
        """Intercepte les clics sur l'icône play (triangle) dans la liste des segments."""
        if obj == self.segments_list.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and self.playing_row >= 0:
                pos = event.pos()
                item = self.segments_list.itemAt(pos)
                if item:
                    row = self.segments_list.row(item)
                    if row == self.playing_row:
                        # Calculer la zone du triangle (icône play)
                        item_rect = self.segments_list.visualItemRect(item)
                        total_width = item_rect.width()
                        col1_width = int(total_width * 0.40)
                        col2_x = item_rect.left() + col1_width
                        icon_x = col2_x + 3      # BAR_MARGIN
                        icon_y = item_rect.top() + (item_rect.height() - 12) // 2  # ICON_SIZE
                        icon_size = 12
                        # Vérifier si le clic est dans le triangle
                        if (icon_x <= pos.x() <= icon_x + icon_size and
                                icon_y <= pos.y() <= icon_y + icon_size):
                            # Toggle play / pause
                            if (self.media_player.playbackState()
                                    == QMediaPlayer.PlaybackState.PlayingState):
                                self.media_player.pause()
                            else:
                                self.media_player.play()
                            return True  # Événement consommé
        return super().eventFilter(obj, event)
    
    def _on_media_status_changed(self, status):
        """Callback quand le statut du média change (pour auto-play)."""
        from PyQt6.QtMultimedia import QMediaPlayer
        
        # EndOfMedia = lecture terminée naturellement
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.auto_play_enabled:
                # Lancer le timer pour jouer le suivant après 500ms
                self.auto_play_timer.start(500)
    
    def _toggle_auto_play(self, enabled):
        """Active/désactive la lecture automatique."""
        self.auto_play_enabled = enabled
        
        if enabled:
            self.auto_play_checkbox.setStyleSheet("font-weight: bold; color: #00aa00;")
            self.playback_label.setText("🔄 Mode auto activé - Cliquez sur Lecture")
            self.playback_label.setStyleSheet("color: #00aa00; font-weight: bold;")
        else:
            self.auto_play_checkbox.setStyleSheet("font-weight: bold;")
            self.auto_play_timer.stop()  # Arrêter si en attente
            self.playback_label.setText("Mode auto désactivé")
            self.playback_label.setStyleSheet("color: gray;")
    
    def _toggle_juz_mode(self, enabled):
        """Active/désactive le mode Juz (multi-sourate)."""
        self.juz_mode = enabled
        
        if enabled:
            self.juz_mode_checkbox.setStyleSheet("font-weight: bold; color: #8e44ad; background-color: #f0e6f6;")
            self.juz_num_spin.setEnabled(True)
            self.skip_istiadha_checkbox.setEnabled(True)
            self.surah_spin.setEnabled(False)
            self.start_ayah_spin.setValue(1)
            self.start_ayah_spin.setEnabled(False)
            
            self.new_surah_btn.setVisible(True)
            
            # Construire la liste des ayats du Juz
            self._build_juz_ayat_list()
            
            self.progress_label.setText(f"📚 Mode Juz {self.juz_num}: {len(self.juz_ayat_list)} ayats")
            self.progress_label.setStyleSheet("color: #8e44ad; font-weight: bold;")
            
            # Info pour l'utilisateur
            juz_temp_dir = f"juz_{self.juz_num:02d}_temp"
            QMessageBox.information(
                self,
                "📚 Mode Juz activé",
                f"Mode Juz {self.juz_num} activé!\n\n"
                f"📖 {len(self.juz_ayat_list)} ayats détectés dans ce Juz\n\n"
                f"📂 Les segments seront sauvegardés dans:\n"
                f"   {juz_temp_dir}/\n\n"
                f"📤 Après traitement, utilisez 'Transférer' pour\n"
                f"   déplacer les fichiers vers leurs sourates.\n\n"
                "💡 Cochez 'Ignorer Isti'adha' si le 1er segment est\n"
                "   أَعُوذُ بِاللهِ مِنَ الشَّيْطَانِ الرَّجِيمِ"
            )
        else:
            self.juz_mode_checkbox.setStyleSheet("font-weight: bold; color: #8e44ad;")
            self.juz_num_spin.setEnabled(False)
            # Ne pas désactiver skip_istiadha - disponible aussi en mode sourate
            self.surah_spin.setEnabled(True)
            self.start_ayah_spin.setEnabled(True)
            self.juz_ayat_list = []
            
            
            self.progress_label.setText("Mode Juz désactivé")
            self.progress_label.setStyleSheet("")
    
    def _on_juz_num_changed(self, value):
        """Callback quand le numéro de Juz change."""
        self.juz_num = value
        if self.juz_mode:
            self._build_juz_ayat_list()
            self.progress_label.setText(f"📚 Mode Juz {self.juz_num}: {len(self.juz_ayat_list)} ayats")
    
    def _on_skip_istiadha_changed(self, checked):
        """Callback quand l'option Isti'adha change."""
        self.skip_istiadha = checked
        
        # Si des segments sont déjà chargés, recharger la liste pour mettre à jour les labels
        if self.segments_list.count() > 0:
            current_row = self.segments_list.currentRow()
            self._load_existing_surah()
            
            # Restaurer la sélection
            if current_row >= 0 and current_row < self.segments_list.count():
                self.segments_list.setCurrentRow(current_row)
                current_item = self.segments_list.currentItem()
                if current_item:
                    self._on_segment_selected(current_item, None)
        
        # Mettre à jour le label
        offset_text = " (+1 décalage)" if checked else ""
        if self.juz_mode:
            self.progress_label.setText(f"📚 Mode Juz {self.juz_num}: {len(self.juz_ayat_list)} ayats{offset_text}")
        else:
            surah_num = self.surah_spin.value()
            self.progress_label.setText(f"✅ Sourate {surah_num}{offset_text}")
    
    def _build_juz_ayat_list(self):
        """Construit la liste des ayats du Juz courant."""
        self.progress_label.setText(f"⏳ Chargement du Juz {self.juz_num}...")
        QApplication.processEvents()
        
        self.juz_ayat_list = build_juz_ayat_list(self.juz_num)
        
        if not self.juz_ayat_list:
            QMessageBox.warning(
                self,
                "Juz non trouvé",
                f"Aucun ayat trouvé pour le Juz {self.juz_num}.\n\n"
                "Vérifiez que les annotations contiennent les données de ce Juz."
            )
    
    def _transfer_juz_segments(self):
        """Transfère les segments du dossier temporaire vers les dossiers de sourate."""
        
        # Vérifier que le dossier temporaire existe
        juz_temp_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"juz_{self.juz_num:02d}_temp")
        
        if not os.path.exists(juz_temp_dir):
            QMessageBox.warning(
                self,
                "Dossier non trouvé",
                f"Le dossier temporaire n'existe pas:\n{juz_temp_dir}\n\n"
                "Veuillez d'abord segmenter un fichier audio en mode Juz."
            )
            return
        
        # Lister les fichiers MP3 dans le dossier temporaire
        mp3_files = sorted(glob.glob(os.path.join(juz_temp_dir, "*.mp3")))
        
        if not mp3_files:
            QMessageBox.warning(
                self,
                "Aucun fichier",
                f"Aucun fichier MP3 trouvé dans:\n{juz_temp_dir}"
            )
            return
        
        # Vérifier que la liste des ayats correspond
        offset = 1 if self.skip_istiadha else 0
        expected_files = len(self.juz_ayat_list) + offset
        
        if len(mp3_files) != expected_files:
            reply = QMessageBox.warning(
                self,
                "⚠️ Nombre de fichiers différent",
                f"Fichiers trouvés: {len(mp3_files)}\n"
                f"Ayats attendus: {expected_files}\n\n"
                f"Cela peut arriver après des fusions.\n"
                f"Voulez-vous continuer le transfert?\n\n"
                f"⚠️ Seuls les {min(len(mp3_files), expected_files)} premiers\n"
                f"   fichiers seront transférés correctement.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Demander confirmation
        reply = QMessageBox.question(
            self,
            "📤 Confirmer le transfert",
            f"Transférer {len(mp3_files)} fichiers vers leurs sourates?\n\n"
            f"📂 Source: {juz_temp_dir}\n"
            f"📂 Destination: dossiers par sourate (001/, 002/, ...)\n\n"
            f"Les fichiers originaux seront déplacés (pas copiés).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.No:
            return
        
        # Effectuer le transfert
        self.progress_bar.setValue(0)
        self.progress_label.setText("📤 Transfert en cours...")
        QApplication.processEvents()
        
        transferred = 0
        errors = []
        
        for i, mp3_path in enumerate(mp3_files):
            # Calculer l'index dans juz_ayat_list
            ayat_idx = i - offset if self.skip_istiadha else i
            
            if ayat_idx < 0:
                # Premier fichier = Isti'adha, ignorer ou mettre dans un dossier spécial
                # Pour l'instant on le laisse dans le dossier temp
                continue
            
            if ayat_idx >= len(self.juz_ayat_list):
                # Fichier en trop (après fusions excessives)
                errors.append(f"{os.path.basename(mp3_path)}: index hors limites")
                continue
            
            surah, ayah = self.juz_ayat_list[ayat_idx]
            
            # Créer le dossier de sourate si nécessaire
            surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{surah:03d}")
            os.makedirs(surah_dir, exist_ok=True)
            
            # Nom du fichier destination
            dest_filename = f"{ayah:03d}.mp3"
            dest_path = os.path.join(surah_dir, dest_filename)
            
            try:
                # Vérifier si le fichier existe déjà
                if os.path.exists(dest_path):
                    # Ajouter un suffixe pour éviter l'écrasement
                    base, ext = os.path.splitext(dest_filename)
                    counter = 1
                    while os.path.exists(dest_path):
                        dest_path = os.path.join(surah_dir, f"{base}_{counter}{ext}")
                        counter += 1
                
                # Déplacer le fichier
                shutil.move(mp3_path, dest_path)
                transferred += 1
                
            except Exception as e:
                errors.append(f"{os.path.basename(mp3_path)}: {str(e)}")
            
            # Mettre à jour la progression
            progress = int(100 * (i + 1) / len(mp3_files))
            self.progress_bar.setValue(progress)
            self.progress_label.setText(f"📤 Transfert: S{surah}:A{ayah} ({i+1}/{len(mp3_files)})")
            QApplication.processEvents()
        
        # Nettoyer le dossier temporaire s'il est vide
        remaining_files = glob.glob(os.path.join(juz_temp_dir, "*.mp3"))
        if not remaining_files:
            try:
                os.rmdir(juz_temp_dir)
            except:
                pass
        
        # Afficher le résultat
        self.progress_bar.setValue(100)
        
        if errors:
            error_msg = "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... et {len(errors) - 10} autres erreurs"
            
            QMessageBox.warning(
                self,
                "⚠️ Transfert partiel",
                f"✅ {transferred} fichiers transférés\n"
                f"❌ {len(errors)} erreurs:\n\n{error_msg}"
            )
        else:
            # Calculer les sourates concernées
            surahs = set(s for s, a in self.juz_ayat_list)
            surah_list = ", ".join(str(s) for s in sorted(surahs))
            
            QMessageBox.information(
                self,
                "✅ Transfert terminé",
                f"✅ {transferred} fichiers transférés avec succès!\n\n"
                f"📂 Sourates: {surah_list}\n\n"
                f"Les segments sont maintenant dans leurs dossiers respectifs."
            )
        
        self.progress_label.setText(f"✅ Transfert terminé: {transferred} fichiers")
        self.progress_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        
    
    def _play_next_segment(self):
        """Joue le segment suivant (appelé par auto-play timer)."""
        if not self.auto_play_enabled:
            return
        
        current_row = self.segments_list.currentRow()
        total_items = self.segments_list.count()
        
        if current_row < total_items - 1:
            if self.playback_multi_select_mode:
                # Mode verrouillé : garder le segment précédent sélectionné
                prev_item = self.segments_list.item(current_row)
                if prev_item:
                    prev_item.setSelected(True)
            else:
                # Mode normal : désélectionner les autres
                self.segments_list.clearSelection()
            
            # Sélectionner et jouer le segment suivant
            next_row = current_row + 1
            next_item = self.segments_list.item(next_row)
            if next_item:
                next_item.setSelected(True)
                self.segments_list.setCurrentItem(next_item)
            
            # La prévisualisation se met à jour automatiquement via _on_segment_selected
            # Petit délai pour laisser la prévisualisation se charger
            QTimer.singleShot(100, self._play_selected_segment)
        else:
            # Fin de la sourate
            self.playback_label.setText("🔄 Fin de la sourate!")
            self.playback_label.setStyleSheet("color: blue; font-weight: bold;")
    
    def _merge_selected_segments(self):
        """Fusionne les segments sélectionnés en un seul fichier."""
        if not PYDUB_AVAILABLE:
            QMessageBox.warning(self, "Erreur", "pydub n'est pas disponible")
            return
        
        selected_items = self.segments_list.selectedItems()
        if len(selected_items) < 2:
            QMessageBox.warning(
                self, "Sélection requise",
                "Sélectionnez au moins 2 segments consécutifs à fusionner.\n\n"
                "Conseil: Utilisez Ctrl+clic ou Shift+clic pour sélectionner plusieurs segments."
            )
            return
        
        # Récupérer les indices et vérifier qu'ils sont consécutifs
        indices = sorted([self.segments_list.row(item) for item in selected_items])
        for i in range(len(indices) - 1):
            if indices[i + 1] - indices[i] != 1:
                QMessageBox.warning(
                    self, "Non consécutifs",
                    "Les segments sélectionnés doivent être consécutifs."
                )
                return
        
        # Récupérer les chemins des fichiers et les textes
        file_paths = []
        item_texts = []
        for idx in indices:
            item = self.segments_list.item(idx)
            path = item.data(Qt.ItemDataRole.UserRole)
            if not path or not os.path.exists(path):
                QMessageBox.warning(self, "Erreur", f"Fichier non trouvé: {path}")
                return
            file_paths.append(path)
            item_texts.append(item.text())
        
        # Arrêter la lecture si en cours
        self.media_player.stop()
        
        # Déterminer le dossier selon le mode
        output_dir = self._get_output_dir()
        silence_duration = self.keep_spin.value()
        
        # LOG: Début de fusion
        action_logger.log_merge_start(indices, file_paths, item_texts, output_dir, silence_duration)
        action_logger.log_state_snapshot("AVANT FUSION", self.segments_list.count(),
            get_segment_files(output_dir))
        
        try:
            # Afficher la progression initiale sur tous les items concernés
            for idx in indices:
                self._update_progress(0, "🔗 Préparation de la fusion...", idx, 0.05)
            
            # Sauvegarder pour annulation
            backup_data = {
                'indices': indices,
                'files': [],
                'texts': item_texts,
            }
            
            # Sauvegarder une copie de chaque fichier
            backup_dir = create_backup_dir(output_dir, "_backup")
            total_files = len(file_paths)
            
            for i, path in enumerate(file_paths):
                progress = int((i / total_files) * 10)
                op_progress = 0.1 + (i / total_files) * 0.1
                self._update_progress(progress, f"🔗 Sauvegarde backup {i+1}/{total_files}...", 
                                      indices[i], op_progress)
                
                backup_path = os.path.join(backup_dir, os.path.basename(path))
                shutil.copy2(path, backup_path)
                backup_data['files'].append({'original': path, 'backup': backup_path})
            
            # Charger et concaténer les segments avec silence entre eux
            silence_duration = self.keep_spin.value()  # en ms
            silence_segment = AudioSegment.silent(duration=silence_duration)
            combined = AudioSegment.empty()
            
            self._update_progress(10, "🔗 Chargement des segments...")
            
            for i, path in enumerate(file_paths):
                progress = 10 + int((i / total_files) * 40)
                op_progress = 0.2 + (i / total_files) * 0.5
                self._update_progress(progress, f"🔗 Chargement segment {i+1}/{total_files}...",
                                      indices[i], op_progress)
                
                segment = AudioSegment.from_file(path)
                if i > 0 and silence_duration > 0:
                    combined += silence_segment
                combined += segment
            
            # Sauvegarder le fichier fusionné
            self._update_progress(55, "🔗 Export du fichier fusionné...")
            
            first_path = file_paths[0]
            combined.export(first_path, format="mp3")
            
            # Vérifier que le fichier est bien créé et lisible
            self._update_progress(70, "🔗 Vérification du fichier...")
            self._wait_for_file_ready(first_path)
            
            # Supprimer les fichiers suivants
            self._update_progress(80, "🔗 Nettoyage...")
            
            for path in file_paths[1:]:
                if os.path.exists(path):
                    os.remove(path)
            
            # Extraire les noms des ayats fusionnés
            first_name = item_texts[0].split(" | ")[0]
            last_name = item_texts[-1].split(" | ")[0]
            
            # Supprimer les items de la liste (sauf le premier)
            for idx in reversed(indices[1:]):
                self.segments_list.takeItem(idx)
            
            # Mettre à jour le premier item
            first_item = self.segments_list.item(indices[0])
            duration = len(combined) / 1000
            first_item.setText(f"{first_name}→{last_name} | {duration:.1f}s")
            first_item.setData(Qt.ItemDataRole.UserRole, first_path)
            
            # Sauvegarder l'état avant renommage pour annulation
            backup_data['merged_path'] = first_path
            backup_data['merged_text'] = first_item.text()
            
            # Renommer les fichiers suivants
            self._update_progress(90, "🔗 Renommage des fichiers...")
            self._renumber_remaining_files()
            
            # Sauvegarder dans l'historique
            self.merge_history.append(backup_data)
            self.undo_merge_btn.setEnabled(True)
            
            # Finalisation
            self._update_progress(95, "🔗 Finalisation...")
            time.sleep(0.2)
            self._update_progress(100, f"✅ Fusion terminée - Prêt à lire ({len(file_paths)} segments)")
            
            # Effacer les barres de progression sur les items
            self.segment_delegate.clear_all_progress()
            self.segments_list.viewport().update()
            
            self.playback_label.setText(f"✅ Fusionné: {first_name} → {last_name} ({len(file_paths)} segments)")
            self.playback_label.setStyleSheet("color: green; font-weight: bold;")
            
            # Désactiver le verrouillage et les marques (la structure a changé)
            self.lock_ayat_checkbox.setChecked(False)
            self.bookmarked_rows.clear()
            self.bookmark_btn.setText("⭐ Marquer")
            self.bookmark_btn.setStyleSheet("padding: 2px 8px; font-size: 12px;")
            
            # Nettoyer l'étoile du texte du segment fusionné
            merged_text = first_item.text()
            if merged_text.startswith("⭐ "):
                first_item.setText(merged_text[3:])
            
            # Effacer toute multi-sélection résiduelle puis sélectionner le segment fusionné
            self.segments_list.clearSelection()
            self.segments_list.setCurrentItem(first_item)
            self.auto_deselect_after_play = True  # Désélectionner quand la lecture se termine
            self._play_selected_segment(first_item)
            
            # LOG: Fusion terminée
            action_logger.log_merge_complete(
                first_path, first_item.text(), int(duration * 1000),
                [f['backup'] for f in backup_data['files']]
            )
            action_logger.log_state_snapshot("APRÈS FUSION", self.segments_list.count(),
                get_segment_files(output_dir))
            
            QMessageBox.information(
                self, "Fusion réussie",
                f"✅ {len(file_paths)} segments fusionnés!\n\n"
                f"{first_name} → {last_name}\n"
                f"Durée: {duration:.1f}s\n"
                f"Silence entre segments: {silence_duration}ms\n\n"
                "Le fichier est prêt à être lu.\n"
                "Cliquez sur '↩️ Annuler fusion' pour restaurer."
            )
            
        except Exception as e:
            # LOG: Erreur de fusion
            action_logger.log_merge_error(str(e), {
                "indices": indices,
                "file_paths": file_paths,
                "output_dir": output_dir
            })
            
            # Effacer les barres de progression en cas d'erreur
            self.segment_delegate.clear_all_progress()
            self.segments_list.viewport().update()
            QMessageBox.critical(self, "Erreur de fusion", str(e))
    
    def _undo_merge(self):
        """Annule la dernière fusion."""
        if not self.merge_history:
            QMessageBox.warning(self, "Aucune fusion", "Aucune fusion à annuler.")
            return
        
        backup_data = self.merge_history.pop()
        
        # LOG: Annulation de fusion
        action_logger.log_undo_merge(backup_data)
        
        try:
            # Déterminer le dossier selon le mode
            output_dir = self._get_output_dir()
            
            # Calculer le décalage: nombre de fichiers fusionnés - 1
            num_merged = len(backup_data['files'])
            shift = num_merged - 1  # Ex: fusion de 2 fichiers = décalage de 1
            
            if shift > 0:
                # Trouver le premier fichier qui a été fusionné
                first_original = backup_data['files'][0]['original']
                first_num = int(os.path.basename(first_original).replace(".mp3", ""))
                
                # Trouver tous les fichiers APRÈS le point de fusion
                # (fichiers avec numéro > first_num, qui ont été décalés)
                all_files = sorted(glob.glob(os.path.join(output_dir, "[0-9][0-9][0-9].mp3")), reverse=True)
                
                # Décaler vers le haut (en commençant par la fin pour éviter les conflits)
                for mp3_file in all_files:
                    file_num = int(os.path.basename(mp3_file).replace(".mp3", ""))
                    # Seuls les fichiers après le premier fusionné doivent être décalés
                    if file_num > first_num:
                        new_num = file_num + shift
                        new_path = os.path.join(output_dir, f"{new_num:03d}.mp3")
                        os.rename(mp3_file, new_path)
            
            # Restaurer les fichiers originaux depuis le backup
            for file_info in backup_data['files']:
                backup_path = file_info['backup']
                original_path = file_info['original']
                
                if os.path.exists(backup_path):
                    # Supprimer le fichier fusionné s'il existe encore
                    if os.path.exists(original_path):
                        os.remove(original_path)
                    shutil.move(backup_path, original_path)
            
            # Nettoyer le dossier backup
            backup_dir = os.path.join(output_dir, "_backup")
            if os.path.exists(backup_dir) and not os.listdir(backup_dir):
                os.rmdir(backup_dir)
            
            # Recharger la sourate pour rafraîchir la liste
            self._load_existing_surah()
            
            self.playback_label.setText("↩️ Fusion annulée - Segments restaurés")
            self.playback_label.setStyleSheet("color: blue; font-weight: bold;")
            
            # Mettre à jour le bouton annuler
            if not self.merge_history:
                self.undo_merge_btn.setEnabled(False)
            
            QMessageBox.information(
                self, "Annulation réussie",
                f"✅ {len(backup_data['files'])} segments restaurés!"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'annulation", str(e))
    
    def _undo_split(self):
        """Annule la dernière division."""
        if not self.split_history:
            QMessageBox.warning(self, "Aucune division", "Aucune division à annuler.")
            return
        
        backup_data = self.split_history.pop()
        
        # LOG: Annulation de division
        action_logger.log_undo_split(backup_data)
        
        try:
            output_dir = backup_data['output_dir']
            original_file = backup_data['original_file']
            original_backup = backup_data['original_backup']
            new_file = backup_data['new_file']
            current_num = backup_data['current_num']
            
            self.progress_bar.setValue(10)
            self.progress_label.setText("↩️ Restauration du fichier original...")
            QApplication.processEvents()
            
            # 1. Supprimer le fichier créé par la division (partie 2)
            if os.path.exists(new_file):
                os.remove(new_file)
            
            self.progress_bar.setValue(30)
            self.progress_label.setText("↩️ Restauration du fichier original...")
            QApplication.processEvents()
            
            # 2. Restaurer le fichier original depuis le backup
            if os.path.exists(original_backup):
                if os.path.exists(original_file):
                    os.remove(original_file)
                shutil.move(original_backup, original_file)
            
            self.progress_bar.setValue(50)
            self.progress_label.setText("↩️ Renommage des fichiers suivants...")
            QApplication.processEvents()
            
            # 3. Décaler tous les fichiers suivants vers le bas (inverse de la division)
            # Trouver tous les fichiers avec un numéro > current_num + 1
            all_files = sorted(glob.glob(os.path.join(output_dir, "[0-9][0-9][0-9].mp3")))
            
            for mp3_file in all_files:
                file_num = int(os.path.basename(mp3_file).replace(".mp3", ""))
                if file_num > current_num + 1:
                    new_num = file_num - 1
                    new_path = os.path.join(output_dir, f"{new_num:03d}.mp3")
                    if not os.path.exists(new_path):
                        os.rename(mp3_file, new_path)
            
            self.progress_bar.setValue(80)
            self.progress_label.setText("↩️ Rechargement de la liste...")
            QApplication.processEvents()
            
            # 4. Nettoyer le dossier backup s'il est vide
            backup_dir = os.path.join(output_dir, "_split_backup")
            if os.path.exists(backup_dir):
                remaining = os.listdir(backup_dir)
                if not remaining:
                    os.rmdir(backup_dir)
            
            # 5. Recharger la liste
            self._load_existing_surah()
            
            self.progress_bar.setValue(100)
            self.progress_label.setText("✅ Division annulée")
            
            self.playback_label.setText("↩️ Division annulée - Segment restauré")
            self.playback_label.setStyleSheet("color: blue; font-weight: bold;")
            
            # Mettre à jour le bouton annuler
            if not self.split_history:
                self.undo_split_btn.setEnabled(False)
            
            QMessageBox.information(
                self, "Annulation réussie",
                f"✅ Division annulée!\n\n"
                f"Le segment original a été restauré."
            )
            
        except Exception as e:
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Erreur d'annulation", str(e))
    
    def _delete_segment(self):
        """Supprime le segment sélectionné et renumérote les fichiers suivants."""
        selected_items = self.segments_list.selectedItems()
        if len(selected_items) != 1:
            QMessageBox.warning(
                self, "Sélection requise",
                "Sélectionnez exactement 1 segment à supprimer."
            )
            return
        
        item = selected_items[0]
        file_path = item.data(Qt.ItemDataRole.UserRole)
        current_idx = self.segments_list.row(item)
        
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Erreur", f"Fichier non trouvé: {file_path}")
            return
        
        # Demander confirmation
        item_text = item.text().split(" | ")[0]
        reply = QMessageBox.question(
            self,
            "🗑️ Confirmer la suppression",
            f"Voulez-vous vraiment supprimer ce segment?\n\n"
            f"📁 {item_text}\n"
            f"📂 {os.path.basename(file_path)}\n\n"
            f"⚠️ Cette action est irréversible!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.No:
            return
        
        # Arrêter la lecture si en cours
        self.media_player.stop()
        
        try:
            output_dir = self._get_output_dir()
            
            self._update_progress(10, "🗑️ Suppression du fichier...")
            os.remove(file_path)
            
            self._update_progress(30, "🗑️ Renommage des fichiers suivants...")
            
            # Récupérer le numéro du fichier supprimé
            deleted_num = int(os.path.basename(file_path).replace(".mp3", ""))
            
            # Renommer tous les fichiers suivants (décalage vers le bas)
            all_files = sorted(glob.glob(os.path.join(output_dir, "[0-9][0-9][0-9].mp3")))
            
            files_to_rename = []
            for mp3_file in all_files:
                file_num = int(os.path.basename(mp3_file).replace(".mp3", ""))
                if file_num > deleted_num:
                    files_to_rename.append((mp3_file, file_num))
            
            # Renommer dans l'ordre (du plus petit au plus grand)
            for mp3_file, file_num in files_to_rename:
                new_num = file_num - 1
                new_path = os.path.join(output_dir, f"{new_num:03d}.mp3")
                os.rename(mp3_file, new_path)
            
            self._update_progress(80, "🗑️ Rechargement de la liste...")
            self._load_existing_surah()
            
            # Sélectionner le segment suivant (ou précédent si c'était le dernier)
            new_count = self.segments_list.count()
            if new_count > 0:
                new_idx = min(current_idx, new_count - 1)
                self.segments_list.setCurrentRow(new_idx)
            
            self._update_progress(100, "✅ Segment supprimé")
            
            # LOG: Suppression
            renamed_files = [(mp3, os.path.join(output_dir, f"{num-1:03d}.mp3")) 
                             for mp3, num in files_to_rename]
            action_logger.log_delete(file_path, item_text, current_idx, renamed_files)
            action_logger.log_state_snapshot("APRÈS SUPPRESSION", self.segments_list.count(),
                get_segment_files(output_dir))
            
            self.playback_label.setText(f"🗑️ Segment {item_text} supprimé")
            self.playback_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
            
            QMessageBox.information(
                self, "Suppression réussie",
                f"✅ Segment supprimé!\n\n"
                f"{item_text}\n\n"
                f"Les fichiers suivants ont été renommés."
            )
            
        except Exception as e:
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Erreur de suppression", str(e))
    
    def _insert_missing_segment(self):
        """Ouvre le dialogue avancé pour récupérer un segment perdu."""
        if not PYDUB_AVAILABLE:
            QMessageBox.warning(self, "Erreur", "pydub n'est pas disponible")
            return
        
        # Arrêter la lecture et ouvrir le dialogue de récupération
        self.media_player.stop()
        dialog = RecoverSegmentDialog(
            output_dir=self._get_output_dir(),
            backup_history=self.merge_history,
            parent=self
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Recharger la liste après insertion
            self._load_existing_surah()
            
            position = dialog.get_insert_position()
            if position:
                self.playback_label.setText(f"✅ Segment inséré à la position {position}")
                self.playback_label.setStyleSheet("color: #27ae60; font-weight: bold;")
    
    def _renumber_remaining_files(self):
        """Renumérote les fichiers restants après une fusion.
        
        IMPORTANT: Utilise des fichiers temporaires pour éviter les conflits
        et la perte de données lors du renommage.
        """
        output_dir = self._get_output_dir()
        start_ayah = self.start_ayah_spin.value() if not self.juz_mode else 0
        
        # Phase 1: Renommer tous les fichiers vers des noms temporaires
        # pour éviter les conflits de nommage
        temp_mappings = []  # Liste de (temp_path, final_path, item, new_text)
        
        for i in range(self.segments_list.count()):
            item = self.segments_list.item(i)
            current_path = item.data(Qt.ItemDataRole.UserRole)
            
            if not current_path or not os.path.exists(current_path):
                continue
            
            if self.juz_mode:
                segment_num = i + 1
                expected_path = os.path.join(output_dir, f"{segment_num:03d}.mp3")
                old_text = item.text()
                duration_part = old_text.split(" | ")[-1] if " | " in old_text else ""
                new_text = f"📚 Segment {segment_num:03d} | {duration_part}"
            else:
                expected_file_num = start_ayah + i
                expected_path = os.path.join(output_dir, f"{expected_file_num:03d}.mp3")
                new_text = None  # Sera calculé plus tard
            
            if current_path != expected_path:
                # Renommer vers un fichier temporaire d'abord
                temp_path = os.path.join(output_dir, f"_temp_rename_{i:03d}.mp3")
                os.rename(current_path, temp_path)
                temp_mappings.append((temp_path, expected_path, item, new_text, i))
        
        # Phase 2: Renommer les fichiers temporaires vers leurs noms finaux
        for temp_path, final_path, item, new_text, i in temp_mappings:
            os.rename(temp_path, final_path)
            item.setData(Qt.ItemDataRole.UserRole, final_path)
            
            if self.juz_mode and new_text:
                item.setText(new_text)
            elif not self.juz_mode:
                # Mode normal: mettre à jour le texte
                surah_num = self.surah_spin.value()
                old_text = item.text()
                duration_part = old_text.split(" | ")[-1] if " | " in old_text else ""
                
                # Calculer l'ayah display selon skip_istiadha, Sourate 1 et 9
                if self.skip_istiadha and i == 0:
                    ayah_display = "Isti'adha"
                elif surah_num == 1:
                    ayah_num = i if self.skip_istiadha else i + 1
                    ayah_display = f"A{ayah_num:03d}"
                elif surah_num == 9:
                    ayah_num = i if self.skip_istiadha else i + 1
                    ayah_display = f"A{ayah_num:03d}"
                else:
                    ayah_num = (i - 1) if self.skip_istiadha else i
                    if ayah_num == 0:
                        ayah_display = "Basmala"
                    else:
                        ayah_display = f"A{ayah_num:03d}"
                
                item.setText(f"S{surah_num:03d}:{ayah_display} | {duration_part}")
        
        # LOG: Renommages effectués
        if temp_mappings:
            action_logger.log_renumber(output_dir, 
                [(m[0].replace("_temp_rename_", ""), m[1]) for m in temp_mappings])
    
    def _split_segment(self):
        """Divise un segment en 2 parties (pour séparer 2 ayats dans un même morceau)."""
        if not PYDUB_AVAILABLE:
            QMessageBox.warning(self, "Erreur", "pydub n'est pas disponible")
            return
        
        selected_items = self.segments_list.selectedItems()
        if len(selected_items) != 1:
            QMessageBox.warning(
                self, "Sélection requise",
                "Sélectionnez exactement 1 segment à diviser."
            )
            return
        
        item = selected_items[0]
        file_path = item.data(Qt.ItemDataRole.UserRole)
        
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Erreur", f"Fichier non trouvé: {file_path}")
            return
        
        # Arrêter la lecture si en cours
        self.media_player.stop()
        
        try:
            # Obtenir le texte de l'ayat pour l'afficher dans le dialogue
            item_text = item.text()
            surah_num = self.surah_spin.value()
            
            # Extraire l'ayah du texte pour récupérer le texte coranique
            ayat_display_text = ""
            prev_ayat_display_text = ""
            ayah = 0
            try:
                main_part = item_text.split(" | ")[0]
                if "→" in main_part:
                    main_part = main_part.split("→")[0]
                ayah_part = main_part.split(":")[1]
                if ayah_part == "Basmala":
                    ayah = 0
                    ayat_display_text = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
                else:
                    ayah = int(ayah_part.replace("A", ""))
                    quran_df = load_quran_text()
                    if quran_df is not None:
                        ayat_display_text = get_ayat_text(quran_df, surah_num, ayah) or ""
                        # Ayat précédente pour le contexte
                        if ayah > 0:
                            prev_label = "Basmala" if ayah == 1 else f"Ayat {ayah - 1}"
                            prev_text = get_ayat_text(quran_df, surah_num, ayah - 1) or ""
                            if prev_text:
                                prev_ayat_display_text = f"{prev_label}: {prev_text}"
            except:
                pass
            
            # Ouvrir le dialogue de prévisualisation
            dialog = SplitPreviewDialog(file_path, surah_num, ayah, self)
            
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.progress_label.setText("Division annulée")
                return
            
            split_point = dialog.get_split_point()
            if split_point is None:
                self.progress_label.setText("Division annulée")
                return
            
            # Récupérer l'index du segment
            current_idx = self.segments_list.row(item)
            
            # Charger le segment pour le diviser
            self._update_progress(10, "✂️ Chargement du segment...", current_idx, 0.1)
            audio = AudioSegment.from_file(file_path)
            split_ms = int(split_point * 1000)
            
            # Diviser l'audio avec marge de sécurité
            self._update_progress(30, "✂️ Division du segment...", current_idx, 0.3)
            
            # Marge de 200ms (2/10s) - la partie 2 commence un peu avant le point de coupure
            margin_ms = 200
            part1 = audio[:split_ms]
            part2_start = max(0, split_ms - margin_ms)  # Ne pas aller en négatif
            part2 = audio[part2_start:]
            
            duration1 = len(part1) / 1000
            duration2 = len(part2) / 1000
            
            # Déterminer les chemins selon le mode
            output_dir = self._get_output_dir()
            current_num = int(os.path.basename(file_path).replace(".mp3", ""))
            total_items = self.segments_list.count()
            
            # LOG: Début de division
            action_logger.log_split_start(file_path, item.text(), split_point, current_idx)
            action_logger.log_state_snapshot("AVANT DIVISION", total_items,
                get_segment_files(output_dir))
            
            # Sauvegarder pour annulation
            backup_dir = create_backup_dir(output_dir, "_split_backup")
            split_backup = {
                'original_file': file_path,
                'original_backup': os.path.join(backup_dir, os.path.basename(file_path)),
                'current_idx': current_idx,
                'current_num': current_num,
                'output_dir': output_dir,
                'juz_mode': self.juz_mode,
            }
            shutil.copy2(file_path, split_backup['original_backup'])
            
            # Étape 1: Décaler tous les fichiers suivants (du dernier au premier)
            self._update_progress(40, "✂️ Décalage des fichiers suivants...")
            
            for i in range(total_items - 1, current_idx, -1):
                list_item = self.segments_list.item(i)
                old_path = list_item.data(Qt.ItemDataRole.UserRole)
                if old_path and os.path.exists(old_path):
                    old_num = int(os.path.basename(old_path).replace(".mp3", ""))
                    new_num = old_num + 1
                    # Utiliser un nom temporaire pour éviter les conflits
                    temp_path = os.path.join(output_dir, f"_temp_{new_num:03d}.mp3")
                    os.rename(old_path, temp_path)
            
            # Renommer les fichiers temporaires vers leurs noms finaux
            temp_files = sorted(glob.glob(os.path.join(output_dir, "_temp_*.mp3")))
            for temp_path in temp_files:
                final_name = os.path.basename(temp_path).replace("_temp_", "")
                final_path = os.path.join(output_dir, final_name)
                os.rename(temp_path, final_path)
            
            # Étape 2: Sauvegarder la première partie (écrase le fichier original)
            self._update_progress(60, "✂️ Sauvegarde partie 1...")
            part1.export(file_path, format="mp3")
            
            # Étape 3: Sauvegarder la deuxième partie
            self._update_progress(75, "✂️ Sauvegarde partie 2...")
            new_file_path = os.path.join(output_dir, f"{current_num + 1:03d}.mp3")
            part2.export(new_file_path, format="mp3")
            
            # Sauvegarder le nouveau fichier créé dans le backup
            split_backup['new_file'] = new_file_path
            self.split_history.append(split_backup)
            self.undo_split_btn.setEnabled(True)
            
            # Étape 4: Recharger la sourate pour rafraîchir complètement la liste
            self._update_progress(90, "✂️ Rechargement de la liste...")
            self._load_existing_surah()
            
            # Sélectionner le premier segment divisé
            if current_idx < self.segments_list.count():
                self.segments_list.setCurrentRow(current_idx)
            
            time.sleep(0.2)
            
            self.progress_bar.setValue(100)
            self.progress_label.setText(f"✅ Segment divisé en 2 parties")
            
            # Effacer les barres de progression
            self.segment_delegate.clear_all_progress()
            self.segments_list.viewport().update()
            
            self.playback_label.setText(f"✂️ Divisé: {duration1:.1f}s + {duration2:.1f}s")
            self.playback_label.setStyleSheet("color: blue; font-weight: bold;")
            
            # LOG: Division terminée
            action_logger.log_split_complete(
                file_path, file_path, new_file_path,
                int(duration1 * 1000), int(duration2 * 1000)
            )
            action_logger.log_state_snapshot("APRÈS DIVISION", self.segments_list.count(),
                get_segment_files(output_dir))
            
            margin_info = f"(marge: {margin_ms}ms)"
            if self.juz_mode:
                QMessageBox.information(
                    self, "Division réussie",
                    f"✅ Segment divisé en 2 parties!\n\n"
                    f"Partie 1 (Segment {current_num}): {duration1:.1f}s\n"
                    f"Partie 2 (Segment {current_num + 1}): {duration2:.1f}s\n"
                    f"Point de coupure: {split_point:.1f}s {margin_info}\n\n"
                    "La liste a été rechargée."
                )
            else:
                QMessageBox.information(
                    self, "Division réussie",
                    f"✅ Segment divisé en 2 parties!\n\n"
                    f"Partie 1 (Ayat {current_num}): {duration1:.1f}s\n"
                    f"Partie 2 (Ayat {current_num + 1}): {duration2:.1f}s\n"
                    f"Point de coupure: {split_point:.1f}s {margin_info}\n\n"
                    "La liste a été rechargée."
                )
            
        except Exception as e:
            # LOG: Erreur de division
            action_logger.log_split_error(str(e), {
                "file_path": file_path,
                "split_point": split_point,
                "current_idx": current_idx
            })
            
            # Effacer les barres de progression en cas d'erreur
            self.segment_delegate.clear_all_progress()
            self.segments_list.viewport().update()
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Erreur de division", str(e))
    
    def _validate_surah(self):
        """Nettoie le cache et les backups après validation de la sourate."""
        reply = QMessageBox.question(
            self,
            "✅ Valider la Sourate",
            "Cette action va supprimer définitivement:\n"
            "  • Le cache des images d'ayats\n"
            "  • Les backups de fusion (_backup)\n"
            "  • Les backups de division (_split_backup)\n\n"
            "Confirmer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        output_dir = self._get_output_dir()
        deleted_items = []
        
        # Supprimer _backup dans le dossier de sortie
        backup_dir = os.path.join(output_dir, "_backup")
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
            deleted_items.append("_backup")
        
        # Supprimer _split_backup dans le dossier de sortie
        split_backup_dir = os.path.join(output_dir, "_split_backup")
        if os.path.exists(split_backup_dir):
            shutil.rmtree(split_backup_dir)
            deleted_items.append("_split_backup")
        
        # Supprimer le cache des ayats
        if os.path.exists(Config.AYAT_CACHE_DIR):
            shutil.rmtree(Config.AYAT_CACHE_DIR)
            deleted_items.append("ayat_cache")
        
        if deleted_items:
            self.progress_label.setText(
                f"✅ Nettoyé: {', '.join(deleted_items)}"
            )
            self.playback_label.setText("🧹 Sourate validée - Cache et backups nettoyés")
            self.playback_label.setStyleSheet("color: green; font-weight: bold;")
            QMessageBox.information(
                self, "Validation",
                f"✅ Nettoyage terminé:\n  • " + "\n  • ".join(deleted_items)
            )
        else:
            QMessageBox.information(
                self, "Validation",
                "✅ Rien à nettoyer (aucun cache ou backup trouvé)."
            )
    
    def _mark_new_surah(self):
        """Marque le segment sélectionné comme début d'une nouvelle sourate.
        
        En mode Juz: Déplace les segments AVANT la sélection vers leur dossier de sourate,
        puis renumérote les segments restants dans le dossier temporaire.
        """
        selected_items = self.segments_list.selectedItems()
        if len(selected_items) != 1:
            QMessageBox.warning(
                self, "Sélection requise",
                "Sélectionnez exactement 1 segment (la Basmala de la nouvelle sourate)."
            )
            return
        
        item = selected_items[0]
        current_idx = self.segments_list.row(item)
        
        if current_idx == 0 and self.juz_mode:
            # Mode Juz avec premier segment sélectionné = transférer TOUS les segments (dernière sourate)
            self._transfer_final_surah()
            return
        elif current_idx == 0:
            QMessageBox.warning(
                self, "Position invalide",
                "Le premier segment ne peut pas être marqué comme nouvelle sourate.\n"
                "Il n'y a pas de segments précédents à transférer."
            )
            return
        
        # Demander le numéro de la sourate QUI VIENT D'ÊTRE TERMINÉE
        current_surah = self.surah_spin.value()
        
        if self.juz_mode:
            # Mode Juz: demander la sourate terminée (celle qu'on va transférer)
            finished_surah, ok = QInputDialog.getInt(
                self,
                "📖 Sourate terminée",
                f"Les {current_idx} premiers segments appartiennent à quelle sourate?\n\n"
                f"(Ces segments seront déplacés vers le dossier de cette sourate)\n"
                f"(Suggestion: {current_surah})",
                value=current_surah,
                min=1,
                max=114
            )
            
            if not ok:
                return
            
            # Confirmation pour mode Juz
            segments_to_move = current_idx  # Segments AVANT la sélection
            remaining_segments = self.segments_list.count() - current_idx
            
            # Déterminer le numéro d'ayat de départ selon skip_istiadha
            if self.skip_istiadha:
                start_ayah = 0  # Premier segment = Basmala (000.mp3)
            else:
                start_ayah = 1  # Premier segment = Ayat 1 (001.mp3) si pas d'Isti'adha ignorée
            
            reply = QMessageBox.question(
                self,
                "📖 Confirmer le transfert",
                f"📤 Transférer {segments_to_move} segments vers Sourate {finished_surah}?\n\n"
                f"• Segments 1 à {current_idx} → dossier {finished_surah:03d}/\n"
                f"• Premier fichier: {start_ayah:03d}.mp3 (Basmala)\n"
                f"• {remaining_segments} segments restent dans juz_temp\n\n"
                f"Le segment sélectionné deviendra le nouveau Segment 001.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Arrêter la lecture
            self.media_player.stop()
            
            try:
                self.progress_bar.setValue(0)
                self.progress_label.setText("📖 Transfert des segments terminés...")
                QApplication.processEvents()
                
                # Dossier temporaire
                juz_temp_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"juz_{self.juz_num:02d}_temp")
                
                # Créer le dossier de la sourate terminée
                surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{finished_surah:03d}")
                os.makedirs(surah_dir, exist_ok=True)
                
                # Préparer l'historique pour annulation
                transfer_backup = {
                    'surah': finished_surah,
                    'surah_dir': surah_dir,
                    'juz_temp_dir': juz_temp_dir,
                    'transferred_files': [],  # Liste des fichiers déplacés
                    'original_juz_ayat_list': self.juz_ayat_list.copy() if self.juz_ayat_list else [],
                    'previous_surah': current_surah,
                    'segments_count': current_idx,
                }
                
                # 1. Déplacer les segments AVANT la sélection vers la sourate
                for i in range(current_idx):
                    list_item = self.segments_list.item(i)
                    old_path = list_item.data(Qt.ItemDataRole.UserRole)
                    
                    if old_path and os.path.exists(old_path):
                        # Nouveau numéro d'ayat
                        new_ayah = start_ayah + i
                        new_path = os.path.join(surah_dir, f"{new_ayah:03d}.mp3")
                        
                        # Sauvegarder pour annulation
                        transfer_backup['transferred_files'].append({
                            'old_path': old_path,
                            'new_path': new_path,
                            'old_num': int(os.path.basename(old_path).replace(".mp3", ""))
                        })
                        
                        shutil.move(old_path, new_path)
                        
                        progress = int(50 * (i + 1) / current_idx)
                        self.progress_bar.setValue(progress)
                        self.progress_label.setText(f"📤 Transfert {i + 1}/{current_idx}...")
                        QApplication.processEvents()
                
                # 2. Renommer les segments restants (à partir de 001)
                self.progress_bar.setValue(60)
                self.progress_label.setText("🔄 Renommage des segments restants...")
                QApplication.processEvents()
                
                remaining_items = []
                for i in range(current_idx, self.segments_list.count()):
                    list_item = self.segments_list.item(i)
                    old_path = list_item.data(Qt.ItemDataRole.UserRole)
                    remaining_items.append(old_path)
                
                # Renommer avec noms temporaires d'abord (éviter conflits)
                temp_paths = []
                for i, old_path in enumerate(remaining_items):
                    if old_path and os.path.exists(old_path):
                        temp_path = os.path.join(juz_temp_dir, f"_temp_{i:03d}.mp3")
                        os.rename(old_path, temp_path)
                        temp_paths.append(temp_path)
                
                # Puis renommer vers les noms finaux
                for i, temp_path in enumerate(temp_paths):
                    new_num = i + 1  # Commence à 001
                    new_path = os.path.join(juz_temp_dir, f"{new_num:03d}.mp3")
                    os.rename(temp_path, new_path)
                    
                    progress = 60 + int(30 * (i + 1) / len(temp_paths))
                    self.progress_bar.setValue(progress)
                    QApplication.processEvents()
                
                # 3. Mettre à jour juz_ayat_list (supprimer les ayats transférés)
                if self.juz_ayat_list and current_idx <= len(self.juz_ayat_list):
                    # Supprimer les N premiers éléments (ceux qu'on vient de transférer)
                    self.juz_ayat_list = self.juz_ayat_list[current_idx:]
                
                # 4. Recharger la liste
                self.progress_bar.setValue(95)
                self.progress_label.setText("🔄 Rechargement...")
                QApplication.processEvents()
                
                self._load_existing_surah()
                
                # 5. Sélectionner le premier segment pour mettre à jour la prévisualisation
                if self.segments_list.count() > 0:
                    self.segments_list.setCurrentRow(0)
                    # Appeler _on_segment_selected avec le bon item
                    current_item = self.segments_list.currentItem()
                    if current_item:
                        self._on_segment_selected(current_item, None)
                
                self.progress_bar.setValue(100)
                self.progress_label.setText(f"✅ Sourate {finished_surah} transférée!")
                
                self.playback_label.setText(f"✅ S{finished_surah}: {segments_to_move} segments transférés")
                self.playback_label.setStyleSheet("color: green; font-weight: bold;")
                
                # Sauvegarder l'historique pour annulation
                self.transfer_history.append(transfer_backup)
                self.undo_transfer_btn.setEnabled(True)
                
                # Mettre à jour le numéro de sourate pour la suite
                self.surah_spin.setValue(finished_surah + 1)
                
                QMessageBox.information(
                    self,
                    "✅ Transfert réussi",
                    f"✅ Sourate {finished_surah} transférée!\n\n"
                    f"📂 {segments_to_move} fichiers → dossier {finished_surah:03d}/\n"
                    f"📋 {remaining_segments} segments restants dans juz_temp\n\n"
                    f"Continuez le traitement avec la Sourate {finished_surah + 1}.\n\n"
                    f"💡 Utilisez '↩️ Annuler transfert' si besoin."
                )
                
            except Exception as e:
                self.progress_bar.setValue(0)
                QMessageBox.critical(self, "Erreur", f"Erreur lors du transfert: {str(e)}")
        
        else:
            # Mode normal (non-Juz): comportement original
            new_surah, ok = QInputDialog.getInt(
                self,
                "📖 Nouvelle Sourate",
                f"Ce segment sera la Basmala de quelle sourate?\n\n"
                f"(Sourate actuelle: {current_surah})\n"
                f"(Suggestion: {current_surah + 1})",
                value=current_surah + 1,
                min=1,
                max=114
            )
            
            if not ok:
                return
            
            # Confirmation
            segments_to_move = self.segments_list.count() - current_idx
            reply = QMessageBox.question(
                self,
                "Confirmer le déplacement",
                f"📖 Déplacer {segments_to_move} segments vers la Sourate {new_surah}?\n\n"
                f"• Le segment sélectionné deviendra: Basmala (000.mp3)\n"
                f"• Les segments suivants seront renumérotés\n"
                f"• Un nouveau dossier sera créé si nécessaire",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Arrêter la lecture
            self.media_player.stop()
            
            try:
                self.progress_bar.setValue(0)
                self.progress_label.setText("📖 Déplacement des segments...")
                QApplication.processEvents()
                
                # Créer le dossier de la nouvelle sourate
                new_surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{new_surah:03d}")
                os.makedirs(new_surah_dir, exist_ok=True)
                
                # Déplacer les fichiers
                items_to_move = []
                for i in range(current_idx, self.segments_list.count()):
                    list_item = self.segments_list.item(i)
                    old_path = list_item.data(Qt.ItemDataRole.UserRole)
                    items_to_move.append((list_item, old_path))
                
                total = len(items_to_move)
                for idx, (list_item, old_path) in enumerate(items_to_move):
                    if old_path and os.path.exists(old_path):
                        # Nouveau numéro d'ayat (0 = Basmala, 1 = premier ayat, etc.)
                        new_ayah = idx  # 0 pour le premier (Basmala)
                        new_path = os.path.join(new_surah_dir, f"{new_ayah:03d}.mp3")
                        
                        # Déplacer le fichier
                        shutil.move(old_path, new_path)
                        
                        progress = int(100 * (idx + 1) / total)
                        self.progress_bar.setValue(progress)
                        self.progress_label.setText(f"📖 Déplacement {idx + 1}/{total}...")
                        QApplication.processEvents()
                
                # Supprimer les items déplacés de la liste actuelle
                for i in range(self.segments_list.count() - 1, current_idx - 1, -1):
                    self.segments_list.takeItem(i)
                
                self.progress_bar.setValue(100)
                self.progress_label.setText(f"✅ {total} segments déplacés vers S{new_surah:03d}")
                
                # Mettre à jour le compteur de la sourate actuelle
                remaining = self.segments_list.count()
                
                QMessageBox.information(
                    self,
                    "Déplacement réussi",
                    f"✅ {total} segments déplacés vers la Sourate {new_surah}!\n\n"
                    f"• Sourate {current_surah}: {remaining} segments restants\n"
                    f"• Sourate {new_surah}: {total} nouveaux segments\n\n"
                    f"Pour continuer avec la Sourate {new_surah}:\n"
                    f"→ Changez le numéro de sourate à {new_surah}\n"
                    f"→ Cliquez sur 'Charger Sourate'"
                )
                
            except Exception as e:
                self.progress_bar.setValue(0)
                QMessageBox.critical(self, "Erreur", f"Erreur lors du déplacement: {str(e)}")
    
    def _transfer_final_surah(self):
        """Transfère tous les segments restants comme la dernière sourate du Juz."""
        total_segments = self.segments_list.count()
        if total_segments == 0:
            QMessageBox.warning(self, "Aucun segment", "Aucun segment à transférer.")
            return
        
        current_surah = self.surah_spin.value()
        
        # Demander le numéro de la dernière sourate
        final_surah, ok = QInputDialog.getInt(
            self,
            "📖 Dernière Sourate du Juz",
            f"Transférer les {total_segments} segments restants vers quelle sourate?\n\n"
            f"(C'est la dernière sourate du Juz {self.juz_num})\n"
            f"(Suggestion: {current_surah})",
            value=current_surah,
            min=1,
            max=114
        )
        
        if not ok:
            return
        
        # Déterminer le numéro d'ayat de départ
        if self.skip_istiadha:
            start_ayah = 0  # Premier segment = Basmala (000.mp3)
        else:
            start_ayah = 1  # Premier segment = Ayat 1 (001.mp3)
        
        # Confirmation
        reply = QMessageBox.question(
            self,
            "📖 Confirmer le transfert final",
            f"📤 Transférer {total_segments} segments vers Sourate {final_surah}?\n\n"
            f"• Tous les segments → dossier {final_surah:03d}/\n"
            f"• Premier fichier: {start_ayah:03d}.mp3\n"
            f"• Le dossier juz_temp sera vidé\n\n"
            f"⚠️ C'est la dernière sourate du Juz!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Arrêter la lecture
        self.media_player.stop()
        
        try:
            self.progress_bar.setValue(0)
            self.progress_label.setText("📖 Transfert de la dernière sourate...")
            QApplication.processEvents()
            
            # Dossier temporaire
            juz_temp_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"juz_{self.juz_num:02d}_temp")
            
            # Créer le dossier de la sourate
            surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{final_surah:03d}")
            os.makedirs(surah_dir, exist_ok=True)
            
            # Transférer tous les segments
            for i in range(total_segments):
                list_item = self.segments_list.item(i)
                old_path = list_item.data(Qt.ItemDataRole.UserRole)
                
                if old_path and os.path.exists(old_path):
                    new_ayah = start_ayah + i
                    new_path = os.path.join(surah_dir, f"{new_ayah:03d}.mp3")
                    
                    shutil.move(old_path, new_path)
                    
                    progress = int(100 * (i + 1) / total_segments)
                    self.progress_bar.setValue(progress)
                    self.progress_label.setText(f"📤 Transfert {i + 1}/{total_segments}...")
                    QApplication.processEvents()
            
            # Nettoyer le dossier temporaire
            if os.path.exists(juz_temp_dir):
                # Supprimer les fichiers _backup et _split_backup s'ils existent
                for subdir in ['_backup', '_split_backup']:
                    subdir_path = os.path.join(juz_temp_dir, subdir)
                    if os.path.exists(subdir_path):
                        shutil.rmtree(subdir_path)
                
                # Si le dossier est vide, le supprimer
                if not os.listdir(juz_temp_dir):
                    os.rmdir(juz_temp_dir)
            
            # Vider la liste
            self.segments_list.clear()
            
            self.progress_bar.setValue(100)
            self.progress_label.setText(f"✅ Juz {self.juz_num} terminé!")
            
            self.playback_label.setText(f"✅ Sourate {final_surah} transférée - Juz terminé!")
            self.playback_label.setStyleSheet("color: green; font-weight: bold;")
            
            QMessageBox.information(
                self,
                "✅ Juz terminé!",
                f"✅ Juz {self.juz_num} complètement traité!\n\n"
                f"📂 Sourate {final_surah}: {total_segments} fichiers\n"
                f"📁 Dossier: {final_surah:03d}/\n\n"
                f"🎉 Tous les segments ont été transférés!"
            )
            
        except Exception as e:
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Erreur", f"Erreur lors du transfert: {str(e)}")
    
    def _undo_transfer(self):
        """Annule le dernier transfert de sourate."""
        if not self.transfer_history:
            QMessageBox.warning(self, "Aucun transfert", "Aucun transfert à annuler.")
            return
        
        backup_data = self.transfer_history.pop()
        
        surah = backup_data['surah']
        surah_dir = backup_data['surah_dir']
        juz_temp_dir = backup_data['juz_temp_dir']
        transferred_files = backup_data['transferred_files']
        original_juz_ayat_list = backup_data['original_juz_ayat_list']
        previous_surah = backup_data['previous_surah']
        segments_count = backup_data['segments_count']
        
        # Confirmation
        reply = QMessageBox.question(
            self,
            "↩️ Annuler le transfert",
            f"Annuler le transfert de la Sourate {surah}?\n\n"
            f"• {len(transferred_files)} fichiers seront restaurés dans juz_temp\n"
            f"• Le dossier {surah:03d}/ sera vidé\n"
            f"• La prévisualisation sera restaurée",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            # Remettre dans l'historique
            self.transfer_history.append(backup_data)
            return
        
        # Arrêter la lecture
        self.media_player.stop()
        
        try:
            self.progress_bar.setValue(0)
            self.progress_label.setText("↩️ Annulation du transfert...")
            QApplication.processEvents()
            
            # 1. D'abord, renommer les fichiers actuels dans juz_temp avec un préfixe temporaire
            current_files = sorted(glob.glob(os.path.join(juz_temp_dir, "[0-9][0-9][0-9].mp3")))
            temp_renamed = []
            
            for i, mp3_file in enumerate(current_files):
                temp_path = os.path.join(juz_temp_dir, f"_undo_temp_{i:03d}.mp3")
                os.rename(mp3_file, temp_path)
                temp_renamed.append(temp_path)
            
            self.progress_bar.setValue(20)
            self.progress_label.setText("↩️ Restauration des fichiers transférés...")
            QApplication.processEvents()
            
            # 2. Ramener les fichiers transférés vers juz_temp avec leur numéro original
            for i, file_info in enumerate(transferred_files):
                new_path = file_info['new_path']  # Chemin actuel dans surah_dir
                old_num = file_info['old_num']     # Numéro original dans juz_temp
                
                if os.path.exists(new_path):
                    restored_path = os.path.join(juz_temp_dir, f"{old_num:03d}.mp3")
                    shutil.move(new_path, restored_path)
                
                progress = 20 + int(40 * (i + 1) / len(transferred_files))
                self.progress_bar.setValue(progress)
                QApplication.processEvents()
            
            self.progress_bar.setValue(60)
            self.progress_label.setText("↩️ Renommage des segments restants...")
            QApplication.processEvents()
            
            # 3. Renommer les fichiers temporaires avec le bon décalage
            for i, temp_path in enumerate(temp_renamed):
                new_num = segments_count + i + 1  # Décaler après les fichiers restaurés
                final_path = os.path.join(juz_temp_dir, f"{new_num:03d}.mp3")
                os.rename(temp_path, final_path)
                
                progress = 60 + int(20 * (i + 1) / len(temp_renamed))
                self.progress_bar.setValue(progress)
                QApplication.processEvents()
            
            # 4. Supprimer le dossier de sourate s'il est vide
            if os.path.exists(surah_dir) and not os.listdir(surah_dir):
                os.rmdir(surah_dir)
            
            # 5. Restaurer juz_ayat_list
            self.juz_ayat_list = original_juz_ayat_list
            
            # 6. Restaurer le numéro de sourate
            self.surah_spin.setValue(previous_surah)
            
            # 7. Recharger la liste
            self.progress_bar.setValue(90)
            self.progress_label.setText("↩️ Rechargement de la liste...")
            QApplication.processEvents()
            
            self._load_existing_surah()
            
            # 8. Sélectionner le premier segment
            if self.segments_list.count() > 0:
                self.segments_list.setCurrentRow(0)
                current_item = self.segments_list.currentItem()
                if current_item:
                    self._on_segment_selected(current_item, None)
            
            self.progress_bar.setValue(100)
            self.progress_label.setText(f"✅ Transfert de S{surah} annulé!")
            
            self.playback_label.setText(f"↩️ Transfert S{surah} annulé - {len(transferred_files)} fichiers restaurés")
            self.playback_label.setStyleSheet("color: blue; font-weight: bold;")
            
            # Mettre à jour le bouton
            if not self.transfer_history:
                self.undo_transfer_btn.setEnabled(False)
            
            QMessageBox.information(
                self,
                "✅ Annulation réussie",
                f"✅ Transfert de la Sourate {surah} annulé!\n\n"
                f"📂 {len(transferred_files)} fichiers restaurés dans juz_temp\n"
                f"📋 La prévisualisation a été restaurée\n\n"
                f"Vous pouvez maintenant corriger et retransférer."
            )
            
        except Exception as e:
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Erreur d'annulation", str(e))
    
    def _verify_segments(self):
        """Vérifie les segments audio contre le texte du Quran."""
        if self.segments_list.count() == 0:
            QMessageBox.warning(self, "Aucun segment", "Aucun segment à vérifier.")
            return
        
        # Charger le texte du Quran
        quran_df = load_quran_text()
        if quran_df is None:
            QMessageBox.warning(
                self, "Texte non trouvé",
                f"Le fichier {Config.AYATS_CSV} n'a pas été trouvé.\n\n"
                "Impossible de vérifier les segments."
            )
            return
        
        # Collecter les informations des segments
        surah_num = self.surah_spin.value()
        start_ayah = self.start_ayah_spin.value()
        segments_info = []
        
        for i in range(self.segments_list.count()):
            item = self.segments_list.item(i)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            
            # Extraire la durée du texte de l'item
            text = item.text()
            try:
                # Format: "S001:A001 | 0.0s → 5.2s"
                duration_part = text.split("→")[-1].strip()
                duration_sec = float(duration_part.replace("s", ""))
                duration_ms = int(duration_sec * 1000)
            except:
                duration_ms = 0
            
            segments_info.append((duration_ms, file_path))
        
        # Effectuer la vérification
        results = verify_segments(surah_num, start_ayah, segments_info, quran_df)
        
        # Construire le rapport
        report = []
        report.append(f"📊 RAPPORT DE VÉRIFICATION - Sourate {surah_num}")
        report.append("=" * 50)
        report.append("")
        
        # Comptage
        if results['count_match']:
            report.append(f"✅ Comptage: {results['total_segments']} segments = {results['expected_ayats']} ayats attendus")
        else:
            report.append(f"❌ Comptage: {results['total_segments']} segments ≠ {results['expected_ayats']} ayats attendus")
        
        report.append("")
        
        # Anomalies
        if results['anomalies']:
            report.append("⚠️ ANOMALIES DÉTECTÉES:")
            for anomaly in results['anomalies']:
                report.append(f"  {anomaly}")
        else:
            report.append("✅ Aucune anomalie de durée détectée!")
        
        report.append("")
        report.append("─" * 50)
        report.append("Détails (ratio durée réelle/estimée):")
        report.append("")
        
        # Détails (seulement les problématiques ou premiers/derniers)
        for detail in results['details'][:5]:  # Premiers 5
            status_icon = "✅" if detail['status'] == 'ok' else "🔴" if detail['status'] == 'too_short' else "🟡"
            report.append(
                f"  {status_icon} A{detail['ayah']}: {detail['actual_sec']}s "
                f"(ratio: {detail['ratio']}) - {detail['text_preview'][:30]}..."
            )
        
        if len(results['details']) > 10:
            report.append(f"  ... ({len(results['details']) - 10} autres ayats)")
        
        for detail in results['details'][-5:]:  # Derniers 5
            if detail not in results['details'][:5]:
                status_icon = "✅" if detail['status'] == 'ok' else "🔴" if detail['status'] == 'too_short' else "🟡"
                report.append(
                    f"  {status_icon} A{detail['ayah']}: {detail['actual_sec']}s "
                    f"(ratio: {detail['ratio']}) - {detail['text_preview'][:30]}..."
                )
        
        # Afficher le rapport
        report_text = "\n".join(report)
        
        # Dialogue avec résumé
        if results['count_match'] and not results['anomalies']:
            QMessageBox.information(
                self, "✅ Vérification OK",
                f"Tous les {results['total_segments']} segments semblent corrects!\n\n"
                f"Sourate {surah_num}, Ayats {start_ayah} à {start_ayah + results['total_segments'] - 1}"
            )
        else:
            # Créer un dialogue scrollable pour les erreurs
            from PyQt6.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QDialogButtonBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle("🔍 Rapport de vérification")
            dialog.setMinimumSize(600, 400)
            
            layout = QVBoxLayout(dialog)
            
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(report_text)
            text_edit.setStyleSheet("font-family: monospace;")
            layout.addWidget(text_edit)
            
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
            buttons.accepted.connect(dialog.accept)
            layout.addWidget(buttons)
            
            dialog.exec()
    
    # -------------------------------------------------------------------------
    # SAUVEGARDE ET RESTAURATION DE SESSION
    # -------------------------------------------------------------------------
    
    def closeEvent(self, event):
        """Sauvegarde la session à la fermeture."""
        self._save_session()
        event.accept()
    
    def _save_session(self):
        """Sauvegarde l'état actuel dans un fichier JSON."""
        try:
            session = {
                "timestamp": datetime.now().isoformat(),
                "juz_mode": self.juz_mode,
                "juz_num": self.juz_num if self.juz_mode else None,
                "surah_num": self.surah_spin.value() if not self.juz_mode else None,
                "skip_istiadha": self.skip_istiadha,
                "selected_segment": self.segments_list.currentRow(),
                "output_dir": self._get_output_dir(),
                "segment_count": self.segments_list.count(),
            }
            
            os.makedirs(os.path.dirname(Config.SESSION_FILE), exist_ok=True)
            with open(Config.SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(session, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # Ne pas bloquer la fermeture si la sauvegarde échoue
    
    def _check_and_restore_session(self):
        """
        Vérifie s'il y a une session précédente et propose de la restaurer.
        Utilise le log d'actions pour décrire le dernier travail effectué.
        """
        if not os.path.exists(Config.SESSION_FILE):
            return
        
        try:
            with open(Config.SESSION_FILE, "r", encoding="utf-8") as f:
                session = json.load(f)
        except Exception:
            return
        
        # Vérifier que le dossier de sortie existe encore
        output_dir = session.get("output_dir", "")
        if not output_dir or not os.path.exists(output_dir):
            return
        
        # Vérifier qu'il y a encore des segments
        segment_count = session.get("segment_count", 0)
        if segment_count == 0:
            return
        
        # Récupérer la dernière action du log
        last_action = self._get_last_action_from_log()
        
        # Construire le message
        mode_str = "Juz" if session.get("juz_mode") else "Sourate"
        num_str = session.get("juz_num") if session.get("juz_mode") else session.get("surah_num")
        
        msg = (
            f"📁 <b>Session précédente trouvée</b><br><br>"
            f"<b>Mode:</b> {mode_str} {num_str}<br>"
            f"<b>Segments:</b> {segment_count}<br>"
        )
        if last_action:
            msg += f"<b>Dernière action:</b> {last_action}<br>"
        msg += f"<br>Voulez-vous reprendre là où vous en étiez ?"
        
        reply = QMessageBox.question(
            self,
            "Reprendre le travail ?",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._restore_session(session)
        else:
            # Supprimer la session pour ne pas redemander
            try:
                os.remove(Config.SESSION_FILE)
            except Exception:
                pass
    
    def _get_last_action_from_log(self) -> str:
        """Récupère la dernière action du log d'actions."""
        if not os.path.exists(Config.ACTION_LOG_FILE):
            return ""
        try:
            with open(Config.ACTION_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Chercher la dernière ligne avec une action (pas un snapshot)
            for line in reversed(lines):
                if any(emoji in line for emoji in ["🔗", "✂️", "🗑️", "➕", "↩️", "🔢"]):
                    # Extraire le type d'action
                    if "🔗" in line:
                        return "Fusion de segments"
                    elif "✂️" in line:
                        return "Division d'un segment"
                    elif "🗑️" in line:
                        return "Suppression d'un segment"
                    elif "➕" in line:
                        return "Insertion d'un segment"
                    elif "↩️" in line:
                        return "Annulation d'opération"
                    elif "🔢" in line:
                        return "Renommage de fichiers"
                    return line.strip()
            return ""
        except Exception:
            return ""
    
    def _restore_session(self, session: dict):
        """Restaure l'état de la session précédente."""
        try:
            # Restaurer le mode
            self.juz_mode = session.get("juz_mode", False)
            self.juz_num = session.get("juz_num", 30)
            self.skip_istiadha = session.get("skip_istiadha", False)
            
            # Mettre à jour l'interface
            self.juz_mode_checkbox.setChecked(self.juz_mode)
            if self.juz_mode:
                self.juz_num_spin.setValue(self.juz_num)
            else:
                surah_num = session.get("surah_num", 1)
                self.surah_spin.setValue(surah_num)
            
            self.skip_istiadha_checkbox.setChecked(self.skip_istiadha)
            
            # Charger les segments
            self._load_existing_surah()
            
            # Restaurer la sélection
            selected = session.get("selected_segment", 0)
            if 0 <= selected < self.segments_list.count():
                self.segments_list.setCurrentRow(selected)
            
            # Logger la restauration
            action_logger.log_state_snapshot(
                f"SESSION REPRISE - {self._get_output_dir()}",
                self.segments_list.count(),
                get_segment_files(self._get_output_dir())
            )
            
        except Exception as e:
            QMessageBox.warning(
                self,
                "Erreur de restauration",
                f"Impossible de restaurer complètement la session:\n{str(e)}"
            )


# =============================================================================
# PANNEAU D'ADMINISTRATION
# =============================================================================
class AdminPanelDialog(QDialog):
    """Dialogue pour vérifier et gérer le travail du collègue."""
    
    def __init__(self, parent: AudioSplitterWindow):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("🔧 Panneau Admin — Vérifier / Supprimer le travail du collègue")
        self.setMinimumSize(600, 500)
        self.resize(700, 550)
        
        self._setup_ui()
        self._refresh_data()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Titre
        title = QLabel("📋 Sourates déjà traitées")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Légende
        legend = QLabel(
            "🟢 = Local uniquement  |  🔵 = HF uniquement  |  🟣 = Les deux  |  ⚪ = Aucun"
        )
        legend.setStyleSheet("color: #666; font-size: 11px;")
        legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(legend)
        
        # Tableau des sourates
        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Sourate", "Fichiers MP3", "Source", "Taille totale", "Action"])
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 200)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        
        # Boutons globaux
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Rafraîchir HF")
        refresh_btn.setToolTip("Revérifier les sourates sur Hugging Face")
        refresh_btn.clicked.connect(self._refresh_from_hf)
        btn_layout.addWidget(refresh_btn)
        
        delete_all_local_btn = QPushButton("🗑️ Tout supprimer (local)")
        delete_all_local_btn.setToolTip("Supprime TOUS les dossiers de sourates en local")
        delete_all_local_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        delete_all_local_btn.clicked.connect(self._delete_all_local)
        btn_layout.addWidget(delete_all_local_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def _refresh_data(self):
        """Rafraîchit la liste des sourates."""
        self.table.clear()
        
        # Récupérer les données
        local_done = get_local_completed_surahs()
        remote_done = get_remote_completed_surahs()
        all_done = local_done | remote_done
        
        if not all_done:
            item = QTreeWidgetItem(["—", "Aucune sourate traitée", "—", "—", "Segmentez d'abord"])
            self.table.addTopLevelItem(item)
            return
        
        for surah_num in sorted(all_done):
            surah_dir = os.path.join(Config.AUDIO_OUTPUT_DIR, f"{surah_num:03d}")
            mp3_files = glob.glob(os.path.join(surah_dir, "*.mp3")) if os.path.exists(surah_dir) else []
            mp3_count = len(mp3_files)
            
            # Taille totale
            total_size = 0
            for f in mp3_files:
                try:
                    total_size += os.path.getsize(f)
                except:
                    pass
            size_mb = total_size / (1024 * 1024)
            size_str = f"{size_mb:.1f} MB"
            
            # Source
            is_local = surah_num in local_done
            is_remote = surah_num in remote_done
            if is_local and is_remote:
                source = "🟣 Local + HF"
            elif is_local:
                source = "🟢 Local"
            elif is_remote:
                source = "🔵 HF"
            else:
                source = "⚪ —"
            
            # Widget d'action (boutons)
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)
            
            delete_btn = QPushButton("🗑️ Supprimer")
            delete_btn.setProperty("surah_num", surah_num)
            delete_btn.clicked.connect(self._delete_surah)
            delete_btn.setStyleSheet("background-color: #e74c3c; color: white; padding: 2px 8px; font-size: 11px;")
            action_layout.addWidget(delete_btn)
            
            unlock_btn = QPushButton("🔓 Déverrouiller")
            unlock_btn.setProperty("surah_num", surah_num)
            unlock_btn.clicked.connect(self._unlock_surah)
            unlock_btn.setStyleSheet("background-color: #f39c12; color: white; padding: 2px 8px; font-size: 11px;")
            action_layout.addWidget(unlock_btn)
            
            action_layout.addStretch()
            
            item = QTreeWidgetItem([
                str(surah_num),
                str(mp3_count),
                source,
                size_str,
                ""
            ])
            self.table.addTopLevelItem(item)
            self.table.setItemWidget(item, 4, action_widget)
    
    def _delete_surah(self):
        """Supprime une sourate localement."""
        btn = self.sender()
        if not btn:
            return
        surah_num = btn.property("surah_num")
        
        reply = QMessageBox.warning(
            self,
            "Confirmer la suppression",
            f"Supprimer la Sourate {surah_num} localement?\n\n"
            f"Cette action est irréversible!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if delete_surah_locally(surah_num):
                # Retirer aussi du set du parent
                if hasattr(self.parent_window, '_completed_surahs'):
                    self.parent_window._completed_surahs.discard(surah_num)
                QMessageBox.information(self, "Supprimé", f"Sourate {surah_num} supprimée.")
                self._refresh_data()
            else:
                QMessageBox.warning(self, "Erreur", f"Impossible de supprimer la Sourate {surah_num}.")
    
    def _unlock_surah(self):
        """Déverrouille une sourate (la retire du set de complétion)."""
        btn = self.sender()
        if not btn:
            return
        surah_num = btn.property("surah_num")
        
        if hasattr(self.parent_window, '_completed_surahs'):
            self.parent_window._completed_surahs.discard(surah_num)
            QMessageBox.information(
                self,
                "Déverrouillé",
                f"Sourate {surah_num} déverrouillée.\n\n"
                f"Vous pouvez maintenant la re-segmenter."
            )
            self._refresh_data()
    
    def _refresh_from_hf(self):
        """Revérifie HF et rafraîchit la liste."""
        self.table.clear()
        item = QTreeWidgetItem(["⏳", "Vérification en cours...", "Patientez", "—", "—"])
        self.table.addTopLevelItem(item)
        QApplication.processEvents()
        
        remote_done = get_remote_completed_surahs()
        if hasattr(self.parent_window, '_completed_surahs'):
            self.parent_window._completed_surahs |= remote_done
        
        self._refresh_data()
    
    def _delete_all_local(self):
        """Supprime toutes les sourates locales."""
        reply = QMessageBox.warning(
            self,
            "⚠️ SUPPRESSION MASSIVE",
            "Voulez-vous vraiment supprimer TOUTES les sourates locales?\n\n"
            "Cette action est IRRÉVERSIBLE et supprimera tous les fichiers MP3!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            local_done = get_local_completed_surahs()
            deleted = 0
            for surah_num in local_done:
                if delete_surah_locally(surah_num):
                    deleted += 1
                    if hasattr(self.parent_window, '_completed_surahs'):
                        self.parent_window._completed_surahs.discard(surah_num)
            
            QMessageBox.information(self, "Terminé", f"{deleted} sourate(s) supprimée(s).")
            self._refresh_data()


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================
def main():
    """Point d'entrée du module."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = AudioSplitterWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    data_manager.ensure_data()
    main()
