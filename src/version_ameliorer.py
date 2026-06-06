import streamlit as st
import pandas as pd
import cv2
import numpy as np
import os
import json
import re
import copy
import hashlib

from keyboard_handler import setup_keyboard_shortcuts, display_shortcuts_help
from undo_redo_manager import save_state_for_undo, undo, redo, can_undo, can_redo, init_undo_redo

# ==============================================================================
# MODULE 1 : CONFIGURATION ET COUPLAGE GÉOMÉTRIQUE (STRICTEMENT SÉCURISÉ)
# ==============================================================================

st.set_page_config(page_title="Quran Ayat Editor V22.0 - Raccourcis Clavier", layout="wide")

IMAGE_DIR = "data/images"
JSON_DIR = "data/annotations"
MARKER_PATH = "data/marker.png"
HEADER_PATH = "data/entete.png"
CSV_PATH = "data/name_sourat.csv"
CSV_SOMMAIRE_PATH = "data/sommaire.csv"

DIVISIONS = ["start", "Full", "1/8", "1/4", "3/8", "1/2", "5/8", "3/4", "7/8"]

for folder in [IMAGE_DIR, JSON_DIR]:
    if not os.path.exists(folder): os.makedirs(folder)

@st.cache_data
def load_surah_database():
    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        return df.set_index('number')['nameAr'].to_dict()
    return {i: f"Sourate {i}" for i in range(1, 115)}

@st.cache_data
def load_sommaire_database():
    """Charge le sommaire.csv pour obtenir Total_Ayats par sourate."""
    if os.path.exists(CSV_SOMMAIRE_PATH):
        df = pd.read_csv(CSV_SOMMAIRE_PATH)
        return df.set_index('Sourate_Num')['Total_Ayats'].to_dict()
    return {i: 999 for i in range(1, 115)}

SURAH_DB = load_surah_database()
SOMMAIRE_DB = load_sommaire_database()

def find_previous_page_counters(current_page_num):
    prev_page_num = current_page_num - 1
    default_meta = {
        "juz": 1, 
        "hizb": 1, 
        "division": "Full", 
        "starts_at_sourat": 1, 
        "starts_at_ayah": "1",
        "division_anchor_ayah": "1:1"
    }
    if prev_page_num < 0: return 1, 0, default_meta
    prev_pattern = re.compile(rf".*0*{prev_page_num}\.json$")
    prev_file = next((f for f in os.listdir(JSON_DIR) if prev_pattern.match(f.lower())), None)
    if prev_file:
        try:
            with open(os.path.join(JSON_DIR, prev_file), 'r', encoding='utf-8') as f:
                prev_data = json.load(f)
            meta_extracted = prev_data.get("metadata", default_meta)
            if "division_anchor_ayah" not in meta_extracted:
                meta_extracted["division_anchor_ayah"] = f"{meta_extracted.get('starts_at_sourat', 1)}:1"
            if "ayats" in prev_data and prev_data["ayats"]:
                last_ay = prev_data["ayats"][-1]
                s_num = int(last_ay.get("sourat_num", 1))
                try: a_num = int(last_ay.get("ayah", 1))
                except ValueError: a_num = 1
                return s_num, a_num, meta_extracted
        except Exception: pass
    return 1, 0, default_meta

def transform_output_to_v18_structure(v8_results, p_num, base_sourat, base_ayah, inherited_meta):
    new_data = {
        "metadata": {
            "page": p_num, 
            "juz": inherited_meta.get("juz", 1), 
            "hizb": inherited_meta.get("hizb", 1), 
            "division": "Full", 
            "starts_at_sourat": base_sourat, 
            "starts_at_ayah": str(base_ayah + 1),
            "division_anchor_ayah": inherited_meta.get("division_anchor_ayah", "1:1")
        }, 
        "ayats": []
    }
    if not v8_results: return new_data
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
            flat_blocks.append({"sourat_num": active_s, "ayah": str(active_a), "type": "Début" if idx == 0 else "Suite", "coords": rect, "y_center": rect[1] + (rect[3] / 2)})
    if not flat_blocks: return new_data
    flat_blocks.sort(key=lambda x: x["y_center"])
    current_line_idx, last_y_center = 1, flat_blocks[0]["y_center"]
    for item in flat_blocks:
        if item["y_center"] - last_y_center > 65: current_line_idx += 1
        item["line_idx"] = current_line_idx
        last_y_center = item["y_center"]
    for item in flat_blocks:
        matched_ayat = next((ay for ay in new_data["ayats"] if ay["sourat_num"] == item["sourat_num"] and ay["ayah"] == item["ayah"]), None)
        rect_obj = {"line_idx": item["line_idx"], "type": item["type"], "coords": item["coords"]}
        if matched_ayat: matched_ayat["rects"].append(rect_obj)
        else: new_data["ayats"].append({"sourat_num": item["sourat_num"], "ayah": item["ayah"], "rects": [rect_obj]})
    return sort_json_structure_strictly(new_data)

# ==============================================================================
# 📐 SYSTÈME DE TRI STRICT BASÉ SUR LA CLÉ "LINE_IDX" ET LE SENS GAUCHE/DROITE
# ==============================================================================
def sort_json_structure_strictly(data):
    if not data or "ayats" not in data or not data["ayats"]:
        return data
    
    # 1. Trier d'abord tous les polygones internes de chaque Ayat par Ligne puis de gauche à droite (X croissant)
    for ayat in data["ayats"]:
        if "rects" in ayat and ayat["rects"]:
            ayat["rects"].sort(key=lambda r: (int(r["line_idx"]), int(r["coords"][0])))
            
    # 2. Trier les blocs Ayats globaux par ordre physique absolu d'apparition (line_idx puis X)
    def get_ayat_physical_key(ayat):
        if not ayat["rects"]: return (999, 0)
        first_rect = ayat["rects"][0]
        return (int(first_rect["line_idx"]), int(first_rect["coords"][0]))
        
    data["ayats"].sort(key=get_ayat_physical_key)
    return data

# ==============================================================================
# MODULE 2 : MOTEUR DE DÉTECTION NATIF
# ==============================================================================

def robust_fine_tune(img_gray, x, y, w, h, min_w_ratio=0.12):
    if w < 15 or h < 15: return None
    roi = img_gray[max(0,y):min(img_gray.shape[0],y+h), max(0,x):min(img_gray.shape[1],x+w)]
    _, binary = cv2.threshold(roi, 200, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((2,2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    coords = cv2.findNonZero(binary)
    if coords is None: return None
    rx, ry, rw, rh = cv2.boundingRect(coords)
    if rw < (w * min_w_ratio) or rw < 25: return None
    return [int(x + rx), int(y + ry), int(rw), int(rh)]

def process_page_v8_5(img, p_left, p_right, s_y, lh, ih, threshold_m, base_sourat, base_ayah):
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    t_left, t_right = int(p_left), int(w - p_right)
    m_tpl, h_tpl = cv2.imread(MARKER_PATH), cv2.imread(HEADER_PATH)
    headers = []
    if h_tpl is not None:
        res_h = cv2.matchTemplate(img, h_tpl, cv2.TM_CCOEFF_NORMED)
        loc_h = np.where(res_h >= 0.45)
        for pt in zip(*loc_h[::-1]):
            if not any(abs(pt[1] - head['y']) < 50 for head in headers): headers.append({'y': pt[1], 'h': h_tpl.shape[0]})
    headers = sorted(headers, key=lambda x: x['y'])
    markers = []
    if m_tpl is not None:
        res_m = cv2.matchTemplate(img, m_tpl, cv2.TM_CCOEFF_NORMED)
        loc_m = np.where(res_m >= threshold_m)
        for pt in zip(*loc_m[::-1]):
            cx, cy = pt[0] + m_tpl.shape[1]//2, pt[1] + m_tpl.shape[0]//2
            if (t_left - 80) < cx < (t_right + 80):
                if not any(abs(cx-m['cx']) < 25 and abs(cy-m['cy']) < 25 for m in markers): markers.append({'cx': cx, 'cy': cy, 'l': pt[0]})
    data_output, current_segments = [], []
    curr_y, active_s, active_a = int(s_y), base_sourat, base_ayah
    while curr_y + lh <= h:
        is_h = [head for head in headers if abs(head['y'] - curr_y) < (lh/2 + 20)]
        if is_h:
            if current_segments:
                active_a += 1
                data_output.append({"nom_surah": SURAH_DB.get(active_s), "number_ayat": active_a, "segments": current_segments})
                current_segments = []
            active_s += 1; active_a = 0
            curr_y = is_h[0]['y'] + is_h[0]['h'] + 15
            continue
        line_m = sorted([m for m in markers if curr_y - 45 <= m['cy'] <= curr_y + lh + 45], key=lambda x: x['cx'], reverse=True)
        y_ref = int(np.mean([m['cy'] for m in line_m])) - (lh // 2) if line_m else curr_y
        if line_m: curr_y = y_ref
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
            seg = robust_fine_tune(gray, t_left, y_ref, x_cursor - t_left, lh)
            if seg: current_segments.append(seg)
        curr_y += lh + ih
    return data_output

# ==============================================================================
# MODULE 3 : EXÉCUTION STRATÉGIQUE DES DEUX MODULES D'AJUSTEMENTS
# ==============================================================================

# ACTION 1 : AJUSTEMENT HORIZONTAL EXPLICITE (X et W d'après l'exemple de marge)
def execute_horizontal_alignment(data):
    if not data["ayats"]: return data
    
    first_line_rects = []
    for ayat in data["ayats"]:
        for rect in ayat["rects"]:
            if int(rect["line_idx"]) == 1: first_line_rects.append(rect["coords"])
            
    if not first_line_rects and data["ayats"][0]["rects"]:
        first_line_rects.append(data["ayats"][0]["rects"][0]["coords"])
    if not first_line_rects: return data
    
    Xref = min([r[0] for r in first_line_rects])
    Wref = max([r[0] + r[2] for r in first_line_rects]) - Xref
    
    lines_map = {}
    for ayat in data["ayats"]:
        for rect in ayat["rects"]:
            l_idx = int(rect["line_idx"])
            if l_idx not in lines_map: lines_map[l_idx] = []
            lines_map[l_idx].append(rect)
            
    for l_idx, rects in lines_map.items():
        rects.sort(key=lambda r: int(r["coords"][0])) # Tri croissant de gauche à droite
        N = len(rects)
        
        if N == 1:
            rects[0]["coords"][0] = int(Xref)
            rects[0]["coords"][2] = int(Wref)
        else:
            gaps = []
            for k in range(N - 1):
                gaps.append(rects[k+1]["coords"][0] - rects[k]["coords"][2] - rects[k]["coords"][0])
                
            rects[0]["coords"][0] = int(Xref) # Marge gauche simple : x1 = xref
            for k in range(1, N):
                rects[k]["coords"][0] = rects[k-1]["coords"][0] + rects[k-1]["coords"][2] + gaps[k-1]
                
            # Calcul marge droite : soit a la largeur à ajouter au dernier polygone
            a = Wref - (sum(r["coords"][2] for r in rects) + sum(gaps))
            rects[N-1]["coords"][2] += int(a)
            if rects[N-1]["coords"][2] < 35: rects[N-1]["coords"][2] = 35
                
    return sort_json_structure_strictly(data)


# ACTION 2 : AJUSTEMENT VERTICAL EXPLICITE (Y et H d'après l'exemple de polygone 1)
def execute_vertical_alignment(data):
    if not data["ayats"]: return data
    
    lines_map = {}
    for ayat in data["ayats"]:
        for rect in ayat["rects"]:
            l_idx = int(rect["line_idx"])
            if l_idx not in lines_map: lines_map[l_idx] = []
            lines_map[l_idx].append(rect)
            
    for l_idx, rects in lines_map.items():
        rects.sort(key=lambda r: int(r["coords"][0])) # Même ordre de gauche à droite
        N = len(rects)
        
        if N == 1:
            rects[0]["coords"][3] = 105 # si nbre=1 => juste forcer la hauteur a 105
        else:
            # si nbr>1 => extraction du y de premier polygone pour Yref
            Yref = rects[0]["coords"][1]
            for rect in rects:
                rect["coords"][1] = int(Yref) # sinon y=Yref
                rect["coords"][3] = 105       # forcer tout les polygones même H a 105
                
    return sort_json_structure_strictly(data)


def execute_pure_sequential_reindex(data):
    if not data["ayats"]: return data
    curr_s = data["ayats"][0]["sourat_num"]
    try: curr_a = int(data["ayats"][0]["ayah"])
    except ValueError: curr_a = 1
    for i, ayat in enumerate(data["ayats"]):
        if i > 0:
            if str(ayat["ayah"]).lower() == "basmala": continue
            if any(r["type"] == "Début" for r in ayat["rects"]): curr_a += 1
            ayat["sourat_num"], ayat["ayah"] = curr_s, str(curr_a)
    return sort_json_structure_strictly(data)

def propagate_sourat_update(data, changed_ayat_idx, new_sourat_num):
    """
    Propage le changement de numéro de sourate aux ayats suivantes.
    S'arrête quand la sourate est terminée (ayah > Total_Ayats du sommaire.csv).
    """
    if not data["ayats"] or changed_ayat_idx >= len(data["ayats"]):
        return data
    
    max_ayats = SOMMAIRE_DB.get(new_sourat_num, 999)
    
    for i in range(changed_ayat_idx, len(data["ayats"])):
        ayat = data["ayats"][i]
        
        if str(ayat["ayah"]).lower() == "basmala":
            ayat["sourat_num"] = new_sourat_num
            continue
        
        try:
            ayah_num = int(ayat["ayah"])
        except ValueError:
            ayah_num = 1
        
        if ayah_num > max_ayats:
            break
        
        ayat["sourat_num"] = new_sourat_num
    
    return sort_json_structure_strictly(data)

# ==============================================================================
# MODULE 4 : PANNEAU DE CONTRÔLE STICKY & RENDU INTERACTIF SCROLLABLE
# ==============================================================================

st.markdown(
    """
    <style>
        div[data-testid="stColumn"]:nth-of-type(1) {
            position: -webkit-sticky;
            position: sticky;
            top: 1rem;
            align-self: flex-start;
            z-index: 99;
        }
        .scrollable-canvas-container {
            max-height: 62vh;
            max-width: 100%;
            overflow-y: auto;
            overflow-x: hidden;
            border: 2px solid #eaeaea;
            border-radius: 8px;
            padding: 5px;
            background-color: #fcfcfc;
            display: flex;
            justify-content: center;
        }
    </style>
    """,
    unsafe_allow_html=True
)

init_undo_redo()
setup_keyboard_shortcuts()

def save_state_to_history():
    """Wrapper pour compatibilité avec l'ancien code."""
    save_state_for_undo()

display_shortcuts_help()

image_files = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('png', 'jpg'))]) if os.path.exists(IMAGE_DIR) else []

if image_files:
    target_page_key = "input_page_direct_global"
    input_page_target = st.session_state.get(target_page_key, 1)

    matched_file_index = 0
    for idx, filename in enumerate(image_files):
        num_found = re.search(r'(\d+)', filename)
        if num_found and int(num_found.group(1)) == input_page_target:
            matched_file_index = idx
            break

    selected_file = st.sidebar.selectbox("Fichier Image Actif", image_files, index=matched_file_index)
    path_img, path_json = os.path.join(IMAGE_DIR, selected_file), os.path.join(JSON_DIR, os.path.splitext(selected_file)[0] + ".json")
    src_img = cv2.imread(path_img)
    
    if src_img is not None:
        detected_p_num = int(re.search(r'(\d+)', selected_file).group(1)) if re.search(r'(\d+)', selected_file) else 0
        auto_pl, auto_pr = (400, 220) if detected_p_num % 2 == 0 else (220, 380)

        thresh = st.sidebar.slider("Sensibilité Marqueurs", 0.20, 0.60, 0.35)
        ######
        pixel_step_x = st.sidebar.number_input("Pas X (px)", min_value=1, max_value=200, value=10, step=5)
        pixel_step_w = st.sidebar.number_input("Pas W (px)", min_value=0, max_value=200, value=10, step=5)
        ######
        drift_factor = st.sidebar.slider("Dérive Interligne (px par ligne)", -3.0, 5.0, 0.4, step=0.1)

        if 'runtime_file' not in st.session_state or st.session_state.runtime_file != selected_file:
            if os.path.exists(path_json):
                with open(path_json, 'r', encoding='utf-8') as f: st.session_state.current_data = json.load(f)
                if "metadata" in st.session_state.current_data and "division_anchor_ayah" not in st.session_state.current_data["metadata"]:
                    st.session_state.current_data["metadata"]["division_anchor_ayah"] = f"{st.session_state.current_data['metadata'].get('starts_at_sourat', 1)}:1"
            else:
                calculated_sourat, calculated_ayah, inherited_metadata = find_previous_page_counters(detected_p_num)
                v8_raw = process_page_v8_5(src_img, auto_pl, auto_pr, 350, 105, 32, thresh, calculated_sourat, calculated_ayah)
                st.session_state.current_data = transform_output_to_v18_structure(v8_raw, detected_p_num, calculated_sourat, calculated_ayah, inherited_metadata)
            st.session_state.runtime_file = selected_file
            st.session_state.backup_ayats = copy.deepcopy(st.session_state.current_data["ayats"])
            st.session_state.debug_logs = []
            st.session_state.focus_a_idx, st.session_state.focus_r_idx = 0, 0
            st.session_state.history_stack = []

        working_json = st.session_state.current_data
        focus_a_idx = st.session_state.get('focus_a_idx', None)
        focus_r_idx = st.session_state.get('focus_r_idx', None)

        with st.sidebar.expander("🌍 Métadonnées de l'Unité", expanded=False):
            meta = working_json["metadata"]
            meta["page"] = st.number_input("Index Page", value=meta.get("page", detected_p_num), key=f"meta_p_{selected_file}")
            meta["juz"] = st.number_input("Juz (1-30)", 1, 30, int(meta.get("juz", 1)), key=f"meta_j_{selected_file}")
            meta["hizb"] = st.number_input("Hizb (1-60)", 1, 60, int(meta.get("hizb", 1)), key=f"meta_h_{selected_file}")
            meta["division"] = st.selectbox("Division du Hizb", DIVISIONS, index=DIVISIONS.index(meta.get("division", "Full")), key=f"meta_d_{selected_file}")
            meta["division_anchor_ayah"] = st.text_input("Ayat début de la DIVISION (Sourate:Ayat)", value=str(meta.get("division_anchor_ayah", "1:1")), key=f"meta_da_{selected_file}")
            
            st.markdown("**📍 Point d'ancrage local de la page :**")
            meta["starts_at_sourat"] = st.number_input("Sourate de début", 1, 114, int(meta.get("starts_at_sourat", 1)), key=f"meta_ss_{selected_file}")
            meta["starts_at_ayah"] = st.text_input("Ayat exacte de début", value=str(meta.get("starts_at_ayah", "1")), key=f"meta_sa_{selected_file}")

        st.sidebar.subheader("📖 Éditeur de Structure")
        if st.sidebar.button("➕ Créer une nouvelle Ayat", use_container_width=True):
            save_state_to_history()
            st.session_state[target_page_key] = detected_p_num 
            next_s_num = working_json["ayats"][-1]["sourat_num"] if working_json["ayats"] else 1
            try: next_a_num = str(int(working_json["ayats"][-1]["ayah"]) + 1)
            except ValueError: next_a_num = "1"
            working_json["ayats"].append({"sourat_num": next_s_num, "ayah": next_a_num, "rects": [{"line_idx": 1, "type": "Début", "coords": [100, 100, 200, 50]}]})
            working_json = sort_json_structure_strictly(working_json)
            st.session_state.current_data = working_json
            st.session_state.focus_a_idx = len(working_json["ayats"]) - 1
            st.session_state.focus_r_idx = 0
            st.rerun()

        tab_editor, tab_actions = st.sidebar.tabs(["📝 Éditeur Actif", "🛠️ Outils Globaux"])
        
        with tab_actions:
            if st.button("Ajustement HORIZONTAL", use_container_width=True, type="secondary"):
                save_state_to_history()
                st.session_state[target_page_key] = detected_p_num
                working_json = execute_horizontal_alignment(working_json)
                st.session_state.current_data = working_json
                st.rerun()
                
            if st.button("Ajustement VERTICAL", use_container_width=True, type="secondary"):
                save_state_to_history()
                st.session_state[target_page_key] = detected_p_num
                working_json = execute_vertical_alignment(working_json)
                st.session_state.current_data = working_json
                st.rerun()
                
            if st.button("Séquençage des Ayats", use_container_width=True):
                save_state_to_history()
                st.session_state[target_page_key] = detected_p_num
                working_json = execute_pure_sequential_reindex(working_json)
                st.session_state.current_data = working_json
                st.rerun()
            if st.sidebar.button("💾 ENREGISTRER ÉDITION JSON", use_container_width=True):
                working_json = sort_json_structure_strictly(working_json)
                with open(path_json, 'w', encoding='utf-8') as f: json.dump(working_json, f, indent=4, ensure_ascii=False)
                st.session_state.backup_ayats = copy.deepcopy(working_json["ayats"])
                st.sidebar.success("Enregistré et trié avec succès !")

        # ==============================================================================
        # DISPOSITION CENTRALE ET NAVIGATION ZONALE
        # ==============================================================================
        col_ctrl, col_canvas = st.columns([1, 2])

        with col_ctrl:
            st.markdown("### 🎯 Navigation Zonale")
            
            current_num_from_file = int(re.search(r'(\d+)', selected_file).group(1)) if re.search(r'(\d+)', selected_file) else 1
            input_page_target = st.number_input("Entrez le numéro de la page :", min_value=1, max_value=604, value=current_num_from_file, step=1, key=target_page_key)
            if input_page_target != current_num_from_file:
                st.rerun()

            selector_list, selector_map = [], {}
            for a_idx, ay in enumerate(working_json["ayats"]):
                for r_idx, rc in enumerate(ay["rects"]):
                    if str(ay['ayah']).lower() == "basmala":
                        label_sel = f"S{ay['sourat_num']} | BASMALA [P{r_idx + 1}] (L{rc['line_idx']})"
                    else:
                        label_sel = f"S{ay['sourat_num']} | A{ay['ayah']} [P{r_idx + 1}] (L{rc['line_idx']})"
                    selector_list.append(label_sel)
                    selector_map[label_sel] = (a_idx, r_idx)

            current_focused_str = "--- Aucun ---"
            if focus_a_idx is not None and focus_r_idx is not None:
                for opt, coords_idx in selector_map.items():
                    if coords_idx == (focus_a_idx, focus_r_idx):
                        current_focused_str = opt
                        break

            chosen_poly = st.selectbox(
                "Polygone en Focus permanent :", 
                options=["--- Aucun ---"] + selector_list,
                index=(selector_list.index(current_focused_str) + 1) if current_focused_str in selector_list else 0
            )
            if chosen_poly != "--- Aucun ---":
                t_a, t_r = selector_map[chosen_poly]
                if focus_a_idx != t_a or focus_r_idx != t_r:
                    st.session_state.focus_a_idx, st.session_state.focus_r_idx = t_a, t_r
                    st.rerun()

            st.markdown("---")
            
            # Toggle multi-sélection
            if 'multi_select_mode' not in st.session_state:
                st.session_state.multi_select_mode = False
            if 'selected_polygons' not in st.session_state:
                st.session_state.selected_polygons = []
            
            col_ms1, col_ms2 = st.columns([1, 1])
            with col_ms1:
                if st.button("🔘 Multi-sélection" if not st.session_state.multi_select_mode else "✅ Multi-sélection ON", 
                            use_container_width=True,
                            type="primary" if st.session_state.multi_select_mode else "secondary"):
                    st.session_state.multi_select_mode = not st.session_state.multi_select_mode
                    if not st.session_state.multi_select_mode:
                        st.session_state.selected_polygons = []
                    st.rerun()
            with col_ms2:
                if st.session_state.multi_select_mode and len(st.session_state.selected_polygons) > 0:
                    st.info(f"📌 {len(st.session_state.selected_polygons)} sélectionnés")
            
            st.markdown("---")
            
            index_to_delete = None
            if focus_a_idx is not None and focus_a_idx < len(working_json["ayats"]):
                active_ayat = working_json["ayats"][focus_a_idx]
                
                if str(active_ayat['ayah']).lower() == "basmala":
                    title_prop = f"#### ⚙️ Propriétés : S{active_ayat['sourat_num']} BASMALA"
                else:
                    title_prop = f"#### ⚙️ Propriétés : S{active_ayat['sourat_num']} A{active_ayat['ayah']}"
                st.markdown(title_prop)
                
                if focus_r_idx is not None and focus_r_idx < len(active_ayat["rects"]):
                    r_obj_shortcut = active_ayat["rects"][focus_r_idx]
                    
                    c_M1, c_M2, c_t3 = st.columns(3)
                    if c_M1.button("⚡ M1", use_container_width=True):
                        save_state_to_history()
                        r_obj_shortcut["coords"][0], r_obj_shortcut["coords"][2] = 385, 1314
                        st.session_state.current_data = working_json
                        st.rerun()
                    if c_M2.button("⚡ M2", use_container_width=True):
                        save_state_to_history()
                        r_obj_shortcut["coords"][0], r_obj_shortcut["coords"][2] = 200, 1314
                        st.session_state.current_data = working_json
                        st.rerun()
                    if c_t3.button("⚡ T3", use_container_width=True):
                        save_state_to_history()
                        r_obj_shortcut["coords"][2] = max(35, r_obj_shortcut["coords"][2] - 75)
                        st.session_state.current_data = working_json
                        st.rerun()
                        
                    c_Y1, c_Y2 = st.columns(2)
                    if c_Y1.button("⚡ Y-", use_container_width=True):
                        save_state_to_history()
                        r_obj_shortcut["coords"][1] = max(0, r_obj_shortcut["coords"][1] - 10)
                        st.session_state.current_data = working_json
                        st.rerun()
                    if c_Y2.button("⚡ Y+", use_container_width=True):
                        save_state_to_history()
                        r_obj_shortcut["coords"][1] = max(0, r_obj_shortcut["coords"][1] + 10)
                        st.session_state.current_data = working_json
                        st.rerun()
                    
                    c_undo, c_redo = st.columns(2)
                    if c_undo.button("↩️ Annuler (⌘Z)", use_container_width=True, disabled=not can_undo()):
                        if undo():
                            st.rerun()
                    if c_redo.button("↪️ Rétablir (⌘⇧Z)", use_container_width=True, disabled=not can_redo()):
                        if redo():
                            st.rerun()

                prev_sourat_num = active_ayat["sourat_num"]
                new_sourat_num = st.number_input("Sourate Num", 1, 114, value=active_ayat["sourat_num"], key=f"sourat_{focus_a_idx}_{selected_file}")
                
                if new_sourat_num != prev_sourat_num:
                    save_state_to_history()
                    working_json = propagate_sourat_update(working_json, focus_a_idx, new_sourat_num)
                    st.session_state.current_data = working_json
                    st.rerun()
                
                active_ayat["sourat_num"] = new_sourat_num
                active_ayat["ayah"] = st.text_input("Ayat Num", value=active_ayat["ayah"])
                
                if active_ayat["sourat_num"] != meta.get("starts_at_sourat") or active_ayat["ayah"] != meta.get("starts_at_ayah"):
                    st.session_state.current_data = sort_json_structure_strictly(working_json)

                if st.button("➕ Ajouter un polygone", use_container_width=True):
                    save_state_to_history()
                    base_l = active_ayat["rects"][-1]["line_idx"] if active_ayat["rects"] else 1
                    active_ayat["rects"].append({"line_idx": base_l, "type": "Suite", "coords": [100, 100, 200, 50]})
                    st.session_state.current_data = sort_json_structure_strictly(working_json)
                    st.session_state.focus_r_idx = len(active_ayat["rects"]) - 1
                    st.rerun()
                
                if focus_r_idx is not None and focus_r_idx < len(active_ayat["rects"]):
                    rect_obj = active_ayat["rects"][focus_r_idx]
                    g_type = st.columns(2)
                    rect_obj["line_idx"] = g_type[0].number_input("Ligne", value=rect_obj["line_idx"], step=1)
                    rect_obj["type"] = g_type[1].selectbox("Nature", ["Début", "Suite"], index=0 if rect_obj["type"] == "Début" else 1)
                    #◀ Décaler. Rétracter ▶. ➡ Déplacer
                    st.markdown("**Décalage proportionnel gauche :**")
                    c_xgrow, c_x, c_wgrow, c_w, c_move = st.columns(5)

                    if c_xgrow.button("X ▶", use_container_width=True):
                        save_state_to_history()
                        # fixe x1, augmente largeur
                        rect_obj["coords"][0] += pixel_step_x
                        rect_obj["coords"][2] -= pixel_step_x
                        st.session_state.current_data = working_json
                        st.rerun()

                    if c_x.button("X  ◀", use_container_width=True):
                        save_state_to_history()

                        # augmente x seulement
                        rect_obj["coords"][0] -= pixel_step_x
                        rect_obj["coords"][2] += pixel_step_x

                        st.session_state.current_data = working_json
                        st.rerun()

                    if c_wgrow.button("W  ◀", use_container_width=True):
                        save_state_to_history()
                        # fixe w, augmente x
                        #rect_obj["coords"][0] += pixel_step
                        rect_obj["coords"][2] -= pixel_step_w
                        st.session_state.current_data = working_json
                        st.rerun()

                    if c_w.button("W  ▶", use_container_width=True):
                        save_state_to_history()

                        # augmente w seulement
                        #rect_obj["coords"][0] -= pixel_step
                        rect_obj["coords"][2] += pixel_step_w

                        st.session_state.current_data = working_json
                        st.rerun()

                    if c_move.button("➡ Déplacer", use_container_width=True):
                        save_state_to_history()

                        # déplace tout
                        rect_obj["coords"][0] += pixel_step_x
                        rect_obj["coords"][2] += pixel_step_w

                        st.session_state.current_data = working_json
                        st.rerun()
                        
                    c = rect_obj["coords"]
                    g1, g2 = st.columns(2)
                    c[0] = g1.number_input("X", value=c[0])
                    c[1] = g2.number_input("Y", value=c[1])
                    c[2] = g1.number_input("W", value=c[2])
                    c[3] = g2.number_input("H", value=c[3])
                    
                    if st.button("❌ Supprimer ce polygone", use_container_width=True, type="secondary"):
                        save_state_to_history()
                        active_ayat["rects"].pop(focus_r_idx)
                        st.session_state.focus_r_idx = 0
                        st.session_state.current_data = sort_json_structure_strictly(working_json)
                        st.rerun()
                        
                st.markdown("---")
                if st.button("🗑️ Supprimer toute l'Ayat", use_container_width=True, type="secondary"):
                    save_state_to_history()
                    index_to_delete = focus_a_idx

            if index_to_delete is not None:
                working_json["ayats"].pop(index_to_delete)
                working_json = execute_pure_sequential_reindex(working_json)
                st.session_state.focus_a_idx, st.session_state.focus_r_idx = 0, 0
                st.rerun()

        with col_canvas:
            canvas_vis, canvas_overlay = src_img.copy(), src_img.copy()
            selected_polys = st.session_state.get('selected_polygons', [])
            
            for a_idx, ayat in enumerate(working_json["ayats"]):
                hash_seed = f"sourah_{ayat['sourat_num']}_ayah_{ayat['ayah']}"
                hash_digest = hashlib.md5(hash_seed.encode()).digest()
                ayat_color = (int(hash_digest[0] % 180 + 40), int(hash_digest[1] % 180 + 40), int(hash_digest[2] % 180 + 40))
                
                for r_idx, rect_obj in enumerate(ayat["rects"]):
                    coords = rect_obj["coords"]
                    is_primary = (focus_a_idx == a_idx and focus_r_idx == r_idx)
                    is_multi_selected = (a_idx, r_idx) in selected_polys
                    
                    if str(ayat['ayah']).lower() == "basmala":
                        label_text = f"S{ayat['sourat_num']} | BASMALA"
                    else:
                        label_text = f"S{ayat['sourat_num']} A{ayat['ayah']}"
                    
                    # Couleur de bordure selon l'état de sélection
                    if is_primary:
                        border_color, thickness = (0, 0, 0), 5
                    elif is_multi_selected:
                        border_color, thickness = (0, 165, 255), 4  # Orange pour multi-sélection
                    else:
                        border_color, thickness = ayat_color, 2
                    
                    cv2.rectangle(canvas_overlay, (coords[0], coords[1]), (coords[0] + coords[2], coords[1] + coords[3]), ayat_color, -1)
                    cv2.rectangle(canvas_vis, (coords[0], coords[1]), (coords[0] + coords[2], coords[1] + coords[3]), border_color, thickness)
                    cv2.putText(canvas_vis, label_text, (coords[0], coords[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, border_color, 2)

            img_rgb = cv2.cvtColor(cv2.addWeighted(canvas_overlay, 0.25, canvas_vis, 0.75, 0), cv2.COLOR_BGR2RGB)

            from streamlit_image_coordinates import streamlit_image_coordinates
            native_h, native_w = src_img.shape[:2]

            st.markdown('<div class="scrollable-canvas-container">', unsafe_allow_html=True)
            value_click = streamlit_image_coordinates(img_rgb, use_column_width=True, key=f"coords_canvas_{selected_file}")
            st.markdown('</div>', unsafe_allow_html=True)

            if value_click is not None:
                ui_w = value_click.get("width", native_w)
                ui_h = value_click.get("height", native_h)
                
                click_ui_x = value_click["x"]
                click_ui_y = value_click["y"]
                
                scale_x = native_w / ui_w
                scale_y = native_h / ui_h
                
                real_x = int(click_ui_x * scale_x)
                real_y = int(click_ui_y * scale_y)
                
                found_match = False
                multi_mode = st.session_state.get('multi_select_mode', False)
                
                for a_idx, ayat in enumerate(working_json["ayats"]):
                    for r_idx, rect_obj in enumerate(ayat["rects"]):
                        c = rect_obj["coords"]
                        if c[0] <= real_x <= (c[0] + c[2]) and c[1] <= real_y <= (c[1] + c[3]):
                            if multi_mode:
                                # Mode multi-sélection
                                poly_tuple = (a_idx, r_idx)
                                if poly_tuple in st.session_state.selected_polygons:
                                    st.session_state.selected_polygons.remove(poly_tuple)
                                else:
                                    st.session_state.selected_polygons.append(poly_tuple)
                                st.session_state.focus_a_idx = a_idx
                                st.session_state.focus_r_idx = r_idx
                                found_match = True
                                st.rerun()
                            else:
                                # Mode sélection simple
                                if st.session_state.focus_a_idx != a_idx or st.session_state.focus_r_idx != r_idx:
                                    st.session_state.focus_a_idx = a_idx
                                    st.session_state.focus_r_idx = r_idx
                                    found_match = True
                                    st.rerun()
                            break
                    if found_match: break
            
            # Note: Les raccourcis ⌘+Z, ⌘+Shift+Z, ⌘+S sont gérés par JavaScript
            # qui clique automatiquement sur les boutons correspondants