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

import data_manager

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
    """Fenêtre principale du launcher — Design professionnel sombre."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quran Segmentation  —  Launcher")
        self.setMinimumSize(800, 580)
        self.resize(800, 580)
        self._setup_ui()
        self._apply_global_style()

    def _apply_global_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a2e;
            }
            QLabel {
                color: #e0e0e0;
            }
            QGroupBox {
                color: #a0aec0;
                border: 1px solid #2d3748;
                border-radius: 12px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 20px;
                padding: 0 10px;
                color: #a0aec0;
            }
        """)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(20)
        layout.setContentsMargins(50, 35, 50, 35)

        # --- HEADER ---
        header = QWidget()
        header.setStyleSheet("background-color: #16213e; border-radius: 16px;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(30, 25, 30, 25)

        title = QLabel("🕌  Quran Segmentation")
        title.setFont(QFont("Inter", 26, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #ffffff; margin-bottom: 4px;")
        header_layout.addWidget(title)

        subtitle = QLabel("Segmentation de pages  ·  Découpage audio  ·  Collaboration")
        subtitle.setFont(QFont("Inter", 11))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #8892b0; letter-spacing: 1px;")
        header_layout.addWidget(subtitle)

        layout.addWidget(header)

        # --- APPLICATIONS ---
        apps_group = QGroupBox("APPLICATIONS")
        apps_layout = QVBoxLayout(apps_group)
        apps_layout.setSpacing(16)
        apps_layout.setContentsMargins(25, 20, 25, 20)

        # Desktop App Card
        desktop_card = self._create_app_card(
            icon="🖥️",
            title="Desktop App",
            desc="Détection automatique des ayats, ajustement des polygones, correction des numéros de sourate.",
            color="#3b82f6",
            hover="#2563eb",
            callback=self._launch_desktop
        )
        apps_layout.addWidget(desktop_card)

        # Audio Splitter Card
        audio_card = self._create_app_card(
            icon="🎵",
            title="Audio Splitter",
            desc="Segmentation par détection des silences, fusion, division, upload vers Hugging Face.",
            color="#8b5cf6",
            hover="#7c3aed",
            callback=self._launch_audio
        )
        apps_layout.addWidget(audio_card)

        layout.addWidget(apps_group)

        # --- CONFIGURATION ---
        config_group = QGroupBox("CONFIGURATION")
        config_layout = QHBoxLayout(config_group)
        config_layout.setSpacing(20)
        config_layout.setContentsMargins(25, 15, 25, 15)

        settings_btn = QPushButton("⚙️  Paramètres")
        settings_btn.setMinimumHeight(50)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b;
                color: #1a1a2e;
                font-weight: bold;
                font-size: 13px;
                border-radius: 10px;
                padding: 10px 28px;
            }
            QPushButton:hover {
                background-color: #d97706;
                color: #ffffff;
            }
        """)
        settings_btn.clicked.connect(self._open_settings)
        config_layout.addWidget(settings_btn)

        cfg = load_config()
        tpl_ok = sum(1 for v in cfg.get("template_paths", {}).values() if v and os.path.exists(v))
        info = QLabel(
            f"<span style='color:#64748b'>Templates configurés :</span> "
            f"<span style='color:#38bdf8; font-weight:bold'>{tpl_ok}/4</span>  &nbsp;&nbsp;|&nbsp;&nbsp;  "
            f"<span style='color:#64748b'>Audio input :</span> "
            f"<span style='color:#38bdf8; font-weight:bold'>{Path(cfg.get('audio_input_dir', '—')).name}</span>"
        )
        info.setStyleSheet("font-size: 12px;")
        config_layout.addWidget(info, 1)

        layout.addWidget(config_group)

        # --- FOOTER ---
        footer = QLabel(
            "Sélectionnez une application ci-dessus pour commencer le travail de segmentation."
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color: #475569; font-size: 11px; margin-top: 8px;")
        layout.addWidget(footer)
        layout.addStretch()

    def _create_app_card(self, icon: str, title: str, desc: str, color: str, hover: str, callback):
        """Crée une carte d'application cliquable."""
        card = QWidget()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(f"""
            QWidget {{
                background-color: #0f172a;
                border: 2px solid {color};
                border-radius: 14px;
            }}
            QWidget:hover {{
                background-color: #1e293b;
                border: 2px solid {hover};
            }}
        """)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(25, 20, 25, 20)
        card_layout.setSpacing(20)

        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI Emoji", 32))
        icon_label.setStyleSheet("border: none; background: transparent;")
        card_layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        text_layout.addWidget(title_label)

        desc_label = QLabel(desc)
        desc_label.setFont(QFont("Inter", 10))
        desc_label.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        desc_label.setWordWrap(True)
        text_layout.addWidget(desc_label)

        card_layout.addLayout(text_layout, 1)

        arrow = QLabel("›")
        arrow.setFont(QFont("Inter", 24, QFont.Weight.Bold))
        arrow.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        card_layout.addWidget(arrow)

        # Clic sur toute la carte
        card.mousePressEvent = lambda ev: callback()

        return card

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
    # S'assurer que les données sont téléchargées avant de lancer l'interface
    data_manager.ensure_data()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = LauncherWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
