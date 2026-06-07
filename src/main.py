#!/usr/bin/env python3
"""
Quran Segmentation Launcher
============================
Interface principale pour lancer les applications de segmentation
du Coran (Desktop App ou Audio Splitter) et configurer les paramètres.
"""

import sys
import os
import json
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QGroupBox, QDialog, QLineEdit, QFileDialog,
    QMessageBox, QScrollArea, QFormLayout, QSpinBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

# =============================================================================
# CONFIG
# =============================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "data" / "config.json"
DEFAULT_CONFIG = {
    "audio_input_dir": str(PROJECT_ROOT / "data" / "audio" / "input"),
    "template_paths": {
        "entete": str(PROJECT_ROOT / "data" / "entete.png"),
        "marker": str(PROJECT_ROOT / "data" / "marker.png"),
        "mark_thomn": str(PROJECT_ROOT / "data" / "mark_thomn.png"),
        "mark_roboa": str(PROJECT_ROOT / "data" / "mark_roboa.png"),
    },
    "detection_params": {
        "threshold": 0.35,
        "padding_left_even": 385,
        "padding_right_even": 190,
        "padding_left_odd": 200,
        "padding_right_odd": 350,
        "start_y": 350,
        "line_height": 105,
        "inter_height": 32,
    }
}


def load_config() -> dict:
    """Charge la configuration depuis le fichier JSON."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # Fusionner avec les défauts pour garantir tous les champs
            merged = dict(DEFAULT_CONFIG)
            merged.update(saved)
            if "template_paths" in saved:
                merged["template_paths"] = dict(DEFAULT_CONFIG["template_paths"])
                merged["template_paths"].update(saved["template_paths"])
            if "detection_params" in saved:
                merged["detection_params"] = dict(DEFAULT_CONFIG["detection_params"])
                merged["detection_params"].update(saved["detection_params"])
            return merged
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    """Sauvegarde la configuration dans le fichier JSON."""
    os.makedirs(CONFIG_PATH.parent, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# =============================================================================
# DIALOGUE DE PARAMÈTRES
# =============================================================================
class SettingsDialog(QDialog):
    """Dialogue de configuration des templates et paramètres de détection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Paramètres de l'application")
        self.setMinimumSize(700, 550)
        self.resize(750, 600)

        self.cfg = load_config()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Titre
        title = QLabel("⚙️ Configuration des ressources et paramètres")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "Personnalisez les chemins des templates et les paramètres de détection\n"
            "pour adapter l'application à différentes versions du Mushaf."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        # Scroll area pour beaucoup de champs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # --- Section Templates ---
        templates_group = QGroupBox("📐 Images de templates")
        templates_form = QFormLayout(templates_group)

        self.entete_edit = self._create_path_edit(
            self.cfg["template_paths"].get("entete", ""),
            "Images PNG (*.png);;Tous (*)",
            is_file=True
        )
        templates_form.addRow("Entête (entete.png):", self.entete_edit)

        self.marker_edit = self._create_path_edit(
            self.cfg["template_paths"].get("marker", ""),
            "Images PNG (*.png);;Tous (*)",
            is_file=True
        )
        templates_form.addRow("Marqueur (marker.png):", self.marker_edit)

        self.thomn_edit = self._create_path_edit(
            self.cfg["template_paths"].get("mark_thomn", ""),
            "Images PNG (*.png);;Tous (*)",
            is_file=True
        )
        templates_form.addRow("Mark Thômn (mark_thomn.png):", self.thomn_edit)

        self.roboa_edit = self._create_path_edit(
            self.cfg["template_paths"].get("mark_roboa", ""),
            "Images PNG (*.png);;Tous (*)",
            is_file=True
        )
        templates_form.addRow("Mark Roboa (mark_roboa.png):", self.roboa_edit)

        scroll_layout.addWidget(templates_group)

        # --- Section Audio ---
        audio_group = QGroupBox("🎵 Dossier audio")
        audio_form = QFormLayout(audio_group)

        self.audio_edit = self._create_path_edit(
            self.cfg.get("audio_input_dir", ""),
            "",
            is_file=False
        )
        audio_form.addRow("Dossier audio/input:", self.audio_edit)

        scroll_layout.addWidget(audio_group)

        # --- Section Détection ---
        detect_group = QGroupBox("🔍 Paramètres de détection")
        detect_form = QFormLayout(detect_group)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setValue(self.cfg["detection_params"].get("threshold", 0.35))
        detect_form.addRow("Seuil de corrélation:", self.threshold_spin)

        self.pl_even_spin = QSpinBox()
        self.pl_even_spin.setRange(0, 1000)
        self.pl_even_spin.setValue(self.cfg["detection_params"].get("padding_left_even", 385))
        detect_form.addRow("Marge gauche (page paire):", self.pl_even_spin)

        self.pr_even_spin = QSpinBox()
        self.pr_even_spin.setRange(0, 1000)
        self.pr_even_spin.setValue(self.cfg["detection_params"].get("padding_right_even", 190))
        detect_form.addRow("Marge droite (page paire):", self.pr_even_spin)

        self.pl_odd_spin = QSpinBox()
        self.pl_odd_spin.setRange(0, 1000)
        self.pl_odd_spin.setValue(self.cfg["detection_params"].get("padding_left_odd", 200))
        detect_form.addRow("Marge gauche (page impaire):", self.pl_odd_spin)

        self.pr_odd_spin = QSpinBox()
        self.pr_odd_spin.setRange(0, 1000)
        self.pr_odd_spin.setValue(self.cfg["detection_params"].get("padding_right_odd", 350))
        detect_form.addRow("Marge droite (page impaire):", self.pr_odd_spin)

        self.start_y_spin = QSpinBox()
        self.start_y_spin.setRange(0, 2000)
        self.start_y_spin.setValue(self.cfg["detection_params"].get("start_y", 350))
        detect_form.addRow("Y de départ:", self.start_y_spin)

        self.line_h_spin = QSpinBox()
        self.line_h_spin.setRange(50, 300)
        self.line_h_spin.setValue(self.cfg["detection_params"].get("line_height", 105))
        detect_form.addRow("Hauteur de ligne:", self.line_h_spin)

        self.inter_h_spin = QSpinBox()
        self.inter_h_spin.setRange(0, 100)
        self.inter_h_spin.setValue(self.cfg["detection_params"].get("inter_height", 32))
        detect_form.addRow("Hauteur inter-ligne:", self.inter_h_spin)

        scroll_layout.addWidget(detect_group)
        scroll_layout.addStretch()

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # --- Boutons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        reset_btn = QPushButton("🔄 Réinitialiser")
        reset_btn.setToolTip("Restaurer les valeurs par défaut")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(reset_btn)

        save_btn = QPushButton("💾 Sauvegarder")
        save_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 8px 20px;")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("❌ Annuler")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _create_path_edit(self, default_path: str, filter_str: str, is_file: bool):
        """Crée un widget ligne de chemin avec bouton Parcourir."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        edit = QLineEdit(default_path)
        edit.setMinimumWidth(350)
        layout.addWidget(edit, 1)

        browse_btn = QPushButton("📂 ...")
        browse_btn.setMaximumWidth(60)
        browse_btn.clicked.connect(lambda: self._browse(edit, filter_str, is_file))
        layout.addWidget(browse_btn)

        return widget

    def _browse(self, edit: QLineEdit, filter_str: str, is_file: bool):
        """Ouvre un dialogue de sélection de fichier/dossier."""
        current = edit.text()
        if is_file:
            path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un fichier", current, filter_str)
        else:
            path = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier", current)
        if path:
            edit.setText(path)

    def _reset_defaults(self):
        """Réinitialise aux valeurs par défaut."""
        reply = QMessageBox.question(
            self, "Réinitialiser",
            "Restaurer tous les paramètres par défaut ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cfg = dict(DEFAULT_CONFIG)
            save_config(self.cfg)
            self.accept()
            QMessageBox.information(self, "Réinitialisé", "Paramètres par défaut restaurés.\nRouvrez les paramètres pour voir les changements.")

    def _save(self):
        """Sauvegarde la configuration."""
        self.cfg["template_paths"]["entete"] = self.entete_edit.findChild(QLineEdit).text()
        self.cfg["template_paths"]["marker"] = self.marker_edit.findChild(QLineEdit).text()
        self.cfg["template_paths"]["mark_thomn"] = self.thomn_edit.findChild(QLineEdit).text()
        self.cfg["template_paths"]["mark_roboa"] = self.roboa_edit.findChild(QLineEdit).text()
        self.cfg["audio_input_dir"] = self.audio_edit.findChild(QLineEdit).text()

        self.cfg["detection_params"]["threshold"] = self.threshold_spin.value()
        self.cfg["detection_params"]["padding_left_even"] = self.pl_even_spin.value()
        self.cfg["detection_params"]["padding_right_even"] = self.pr_even_spin.value()
        self.cfg["detection_params"]["padding_left_odd"] = self.pl_odd_spin.value()
        self.cfg["detection_params"]["padding_right_odd"] = self.pr_odd_spin.value()
        self.cfg["detection_params"]["start_y"] = self.start_y_spin.value()
        self.cfg["detection_params"]["line_height"] = self.line_h_spin.value()
        self.cfg["detection_params"]["inter_height"] = self.inter_h_spin.value()

        save_config(self.cfg)
        QMessageBox.information(self, "Sauvegardé", "Configuration enregistrée avec succès !")
        self.accept()


# =============================================================================
# FENÊTRE PRINCIPALE
# =============================================================================
class LauncherWindow(QMainWindow):
    """Fenêtre principale du launcher."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🕌 Quran Segmentation — Launcher")
        self.setMinimumSize(700, 500)
        self.resize(700, 500)

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(25)
        layout.setContentsMargins(40, 30, 40, 30)

        # Titre
        title = QLabel("🕌 Quran Segmentation")
        title.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)

        subtitle = QLabel("Outils de segmentation et découpage audio du Coran")
        subtitle.setFont(QFont("Arial", 12))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #7f8c8d; margin-bottom: 20px;")
        layout.addWidget(subtitle)

        # --- Boutons d'application ---
        apps_group = QGroupBox("Lancer une application")
        apps_layout = QVBoxLayout(apps_group)
        apps_layout.setSpacing(20)
        apps_layout.setContentsMargins(30, 25, 30, 25)

        # Desktop App
        desktop_btn = QPushButton("🖥️  Desktop App — Segmentation des pages")
        desktop_btn.setMinimumHeight(70)
        desktop_btn.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        desktop_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border-radius: 10px;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        desktop_btn.clicked.connect(self._launch_desktop)
        apps_layout.addWidget(desktop_btn)

        desktop_desc = QLabel("Détection automatique des ayats, ajustement des polygones, correction des numéros.")
        desktop_desc.setStyleSheet("color: #666; font-size: 11px; padding-left: 10px;")
        apps_layout.addWidget(desktop_desc)

        # Audio Splitter
        audio_btn = QPushButton("🎵 Audio Splitter — Découpage des récitations")
        audio_btn.setMinimumHeight(70)
        audio_btn.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        audio_btn.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad;
                color: white;
                border-radius: 10px;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #732d91;
            }
        """)
        audio_btn.clicked.connect(self._launch_audio)
        apps_layout.addWidget(audio_btn)

        audio_desc = QLabel("Segmentation automatique par détection des silences, fusion, division et upload HF.")
        audio_desc.setStyleSheet("color: #666; font-size: 11px; padding-left: 10px;")
        apps_layout.addWidget(audio_desc)

        layout.addWidget(apps_group)

        # --- Paramètres ---
        settings_group = QGroupBox("Administration & Configuration")
        settings_layout = QHBoxLayout(settings_group)
        settings_layout.setContentsMargins(30, 15, 30, 15)

        settings_btn = QPushButton("⚙️ Paramètres")
        settings_btn.setMinimumHeight(45)
        settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #d68910;
            }
        """)
        settings_btn.clicked.connect(self._open_settings)
        settings_layout.addWidget(settings_btn)

        config_label = QLabel("Configurer les templates, dossier audio et paramètres de détection")
        config_label.setStyleSheet("color: #666;")
        settings_layout.addWidget(config_label, 1)

        layout.addWidget(settings_group)

        # Info config
        cfg = load_config()
        config_info = QLabel(
            f"📁 Audio: {cfg.get('audio_input_dir', '—')}  |  "
            f"📐 Templates: {len([v for v in cfg.get('template_paths', {}).values() if v and os.path.exists(v)])}/4"
        )
        config_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        config_info.setStyleSheet("color: #95a5a6; font-size: 10px; margin-top: 10px;")
        layout.addWidget(config_info)

        # Spacer
        layout.addStretch()

    def _launch_desktop(self):
        """Lance l'application Desktop."""
        script_path = Path(__file__).resolve().parent / "desktop_app.py"
        if not script_path.exists():
            QMessageBox.critical(self, "Erreur", f"Fichier introuvable:\n{script_path}")
            return

        self.setWindowTitle("🕌 Quran Segmentation — Desktop App en cours...")
        subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT)
        )

    def _launch_audio(self):
        """Lance l'application Audio Splitter."""
        script_path = Path(__file__).resolve().parent / "audio_splitter.py"
        if not script_path.exists():
            QMessageBox.critical(self, "Erreur", f"Fichier introuvable:\n{script_path}")
            return

        self.setWindowTitle("🕌 Quran Segmentation — Audio Splitter en cours...")
        subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT)
        )

    def _open_settings(self):
        """Ouvre le dialogue de paramètres."""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Rafraîchir l'affichage des infos
            cfg = load_config()
            for i in range(self.centralWidget().layout().count()):
                widget = self.centralWidget().layout().itemAt(i).widget()
                if isinstance(widget, QLabel) and "📁 Audio" in widget.text():
                    widget.setText(
                        f"📁 Audio: {cfg.get('audio_input_dir', '—')}  |  "
                        f"📐 Templates: {len([v for v in cfg.get('template_paths', {}).values() if v and os.path.exists(v)])}/4"
                    )
                    break


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = LauncherWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
