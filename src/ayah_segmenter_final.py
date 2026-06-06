import streamlit as st
import pandas as pd
import cv2
import numpy as np
import os
import json
import re

import data_manager

# --- CONFIGURATION ---
st.set_page_config(page_title="Quran Precise V8.5", layout="wide")

_BASE = str(data_manager.DATA_DIR)
IMAGE_DIR = os.path.join(_BASE, "images")
MARKER_PATH = os.path.join(_BASE, "marker.png")
HEADER_PATH = os.path.join(_BASE, "entete.png")
CSV_PATH = os.path.join(_BASE, "name_sourat.csv")

@st.cache_data
def load_surah_db():
    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        return df.set_index('number')['nameAr'].to_dict()
    return {i: f"Sourate {i}" for i in range(1, 115)}

SURAH_DB = load_surah_db()

# --- LOGIQUE DE PRÉCISION ---

def robust_fine_tune(img_gray, x, y, w, h, min_w_ratio=0.12):
    """Ajuste le bloc aux pixels et élimine les faux positifs (vides)."""
    if w < 15 or h < 15: return None
    
    # Extraction de la zone avec petite marge
    roi = img_gray[max(0,y):min(img_gray.shape[0],y+h), max(0,x):min(img_gray.shape[1],x+w)]
    
    # Nettoyage (Seuil strict + Morphologie)
    _, binary = cv2.threshold(roi, 200, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((2,2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    coords = cv2.findNonZero(binary)
    if coords is None: return None

    rx, ry, rw, rh = cv2.boundingRect(coords)
    
    # Filtre de taille pour éviter les blocs vides dans les marges
    if rw < (w * min_w_ratio) or rw < 25: 
        return None

    return [int(x + rx), int(y + ry), int(rw), int(rh)]

def process_page_v8_5(img, p_left, p_right, s_y, lh, ih, threshold_m):
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    t_left, t_right = int(p_left), int(w - p_right)
    
    m_tpl = cv2.imread(MARKER_PATH)
    h_tpl = cv2.imread(HEADER_PATH)
    
    # 1. Détection initiale (Headers & Markers)
    headers = []
    if h_tpl is not None:
        res_h = cv2.matchTemplate(img, h_tpl, cv2.TM_CCOEFF_NORMED)
        loc_h = np.where(res_h >= 0.45)
        for pt in zip(*loc_h[::-1]):
            if not any(abs(pt[1] - head['y']) < 50 for head in headers):
                headers.append({'y': pt[1], 'h': h_tpl.shape[0]})
    headers = sorted(headers, key=lambda x: x['y'])

    markers = []
    if m_tpl is not None:
        res_m = cv2.matchTemplate(img, m_tpl, cv2.TM_CCOEFF_NORMED)
        loc_m = np.where(res_m >= threshold_m)
        for pt in zip(*loc_m[::-1]):
            cx, cy = pt[0] + m_tpl.shape[1]//2, pt[1] + m_tpl.shape[0]//2
            if (t_left - 80) < cx < (t_right + 80):
                if not any(abs(cx-m['cx']) < 25 and abs(cy-m['cy']) < 25 for m in markers):
                    markers.append({'cx': cx, 'cy': cy, 'l': pt[0]})

    # 2. Segmentation avec recalage dynamique
    data_output = []
    current_segments = []
    curr_y = int(s_y)
    active_s = st.session_state.get('current_surah_num', 1)
    active_a = st.session_state.get('last_ayah_num', 0)

    while curr_y + lh <= h:
        # Check Titre
        is_h = [head for head in headers if abs(head['y'] - curr_y) < (lh/2 + 20)]
        if is_h:
            if current_segments:
                active_a += 1
                data_output.append({"nom_surah": SURAH_DB.get(active_s), "number_ayat": active_a, "segments": current_segments})
                current_segments = []
            active_s += 1
            active_a = 0
            curr_y = is_h[0]['y'] + is_h[0]['h'] + 15
            continue

        # RECALAGE DYNAMIQUE : On cherche les marqueurs sur cette ligne
        line_m = sorted([m for m in markers if curr_y - 45 <= m['cy'] <= curr_y + lh + 45], 
                        key=lambda x: x['cx'], reverse=True)
        
        # Si on trouve un marqueur, on ajuste curr_y sur sa position réelle
        y_ref = curr_y
        if line_m:
            y_center_real = int(np.mean([m['cy'] for m in line_m]))
            y_ref = y_center_real - (lh // 2)
            curr_y = y_ref # Recalage de la grille pour la ligne suivante

        x_cursor = t_right
        
        if not line_m:
            seg = robust_fine_tune(gray, t_left, y_ref, x_cursor - t_left, lh)
            if seg: current_segments.append(seg)
        else:
            for m in line_m:
                seg = robust_fine_tune(gray, m['l'], y_ref, x_cursor - m['l'], lh)
                if seg:
                    current_segments.append(seg)
                    active_a += 1
                    data_output.append({"nom_surah": SURAH_DB.get(active_s), "number_ayat": active_a, "segments": current_segments})
                    current_segments = []
                x_cursor = m['l']
            
            # Reste à gauche
            seg = robust_fine_tune(gray, t_left, y_ref, x_cursor - t_left, lh)
            if seg: current_segments.append(seg)

        # Progression
        curr_y += lh + ih
    
    return data_output, markers, active_s, active_a

# --- INTERFACE ---
st.sidebar.title("💎 Quran Precise V8.5")
files = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('png', 'jpg'))]) if os.path.exists(IMAGE_DIR) else []

if files:
    sel_file = st.sidebar.selectbox("Fichier", files)
    p_num = int(re.search(r'(\d+)', sel_file).group(1)) if re.search(r'(\d+)', sel_file) else 0
    d_left, d_right = (400, 220) if p_num % 2 == 0 else (220, 380)

    # Paramètres conseillés pour tes photos
    thresh = st.sidebar.slider("Sensibilité Marqueurs", 0.20, 0.60, 0.35)
    pl = st.sidebar.number_input("Marge Gauche", value=d_left)
    pr = st.sidebar.number_input("Marge Droite", value=d_right)
    lh = st.sidebar.number_input("Hauteur Ligne", value=105)
    ih = st.sidebar.number_input("Interligne", value=32)

    if 'current_surah_num' not in st.session_state: st.session_state.current_surah_num = 1
    if 'last_ayah_num' not in st.session_state: st.session_state.last_ayah_num = 0

    img = cv2.imread(os.path.join(IMAGE_DIR, sel_file))
    if img is not None:
        results, m_list, last_s, last_a = process_page_v8_5(img, pl, pr, 350, lh, ih, thresh)
        
        vis = img.copy()
        overlay = img.copy()
        for i, res in enumerate(results):
            c = [(255,100,100), (100,255,100), (100,100,255), (255,255,100)][i % 4]
            for s in res["segments"]:
                cv2.rectangle(overlay, (s[0], s[1]), (s[0]+s[2], s[1]+s[3]), c, -1)
                cv2.rectangle(vis, (s[0], s[1]), (s[0]+s[2], s[1]+s[3]), c, 2)
        
        final = cv2.addWeighted(overlay, 0.25, vis, 0.75, 0)
        for m in m_list: cv2.circle(final, (m['cx'], m['cy']), 8, (0,0,255), -1)
        st.image(cv2.cvtColor(final, cv2.COLOR_BGR2RGB), use_container_width=True)
        
        if st.button("💾 Valider la page"):
            st.session_state.current_surah_num, st.session_state.last_ayah_num = last_s, last_a
            st.success("Page enregistrée.")