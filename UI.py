import streamlit as st
import pandas as pd
import pydeck as pdk
import os
import pickle
import osmnx as ox
import random

# --- 1. パスワード認証 ---
APP_PASSWORD = "114" 

def check_password():
    if "password_correct" not in st.session_state:
        st.title("前橋市 避難所解析システム")
        pwd = st.text_input("パスワードを入力してください", type="password", key="pwd_input")
        if st.button("ログイン"):
            if pwd == APP_PASSWORD:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("パスワードが正しくありません")
        return False
    return True

# --- 2. データ読み込み（キャッシュを利用） ---
CSV_FILE = "emergency_shelter_maebashi.csv"
GRAPH_CACHE = "maebashi_graph.graphml"
RESULT_CACHE_DIR = "cache_results"

@st.cache_resource
def load_graph_edges():
    G = ox.load_graphml(GRAPH_CACHE)
    edges = []
    for u, v, data in G.edges(data=True):
        if 'geometry' in data:
            path = [[lon, lat] for lon, lat in data['geometry'].coords]
        else:
            path = [[G.nodes[u]['x'], G.nodes[u]['y']], [G.nodes[v]['x'], G.nodes[v]['y']]]
        edges.append({"u": u, "v": v, "path": path})
    return edges

def main():
    if not check_password():
        st.stop()

    st.title("前橋市 避難所道路網解析（最終版）")

    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
    except:
        df = pd.read_csv(CSV_FILE, encoding='cp932')

    # --- サイドバー設定 ---
    st.sidebar.header("表示条件")
    ST_COLS = {
        "洪水": "flood", "崖崩れ...": "landslides_debrisflow_medslides",
        "高潮": "storm_surge", "地震": "earthquake", "津波": "tsunami",
        "大規模な火事": "largescale_fire", "内水氾濫": "inlandflooding", "火山現象": "volcanic_phenomena"
    }
    selected_label = st.sidebar.selectbox("災害種類", list(ST_COLS.keys()))
    disaster_col = ST_COLS[selected_label]
    active_shelters = df[df[disaster_col] == True].copy()
    
    n_rank = st.sidebar.number_input(f"何番目に近い施設 (n)", 1, len(active_shelters), 1)

    # --- データの準備 ---
    cache_path = os.path.join(RESULT_CACHE_DIR, f"full_ranks_{disaster_col}.pkl")
    if not os.path.exists(cache_path):
        st.error("解析データ(.pkl)が見つかりません。")
        return

    with st.spinner("地図を構築中..."):
        all_edges = load_graph_edges()
        with open(cache_path, 'rb') as f:
            node_rankings = pickle.load(f)
        
        random.seed(42)
        color_map = {idx: [random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)] 
                     for idx in active_shelters.index}

        path_data = []
        for edge in all_edges:
            ranks = node_rankings.get(edge['u'], [])
            if len(ranks) >= n_rank:
                print(f"Node {edge['u']}only has {len(ranks)} shelters in its list.")
                owner_id = ranks[n_rank-1]
                if owner_id in color_map:
                    path_data.append({
                        "path": edge['path'],
                        "color": color_map[owner_id]
                    })
        
        shelter_data = []
        for idx, row in active_shelters.iterrows():
            shelter_data.append({
                "position": [row['lon'], row['lat']],
                "name": row['name'],
                "fill_color": color_map[idx],
                "line_color": [0, 0, 0] # 外周は常に黒
            })

    # --- Pydeckレイヤー設定 ---
    # 道路レイヤー (pickable=False にしてツールチップを無効化)
    path_layer = pdk.Layer(
        "PathLayer",
        path_data,
        get_path="path",
        get_color="color",
        width_min_pixels=2,
        pickable=False, 
    )

    # 施設レイヤー (pickable=True でツールチップを有効化)
    shelter_layer = pdk.Layer(
        "ScatterplotLayer",
        shelter_data,
        get_position="position",
        get_fill_color="fill_color",
        get_line_color="line_color",
        stroked=True,            # 外周線を描画する
        filled=True,
        line_width_min_pixels=2, # 外周の太さ
        get_radius=100,
        radius_min_pixels=8,     # 点の大きさ
        pickable=True,
    )

    view_state = pdk.ViewState(latitude=36.3895, longitude=139.0634, zoom=12)

    # デックの描画
    st.pydeck_chart(pdk.Deck(
        layers=[path_layer, shelter_layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/light-v9",
        # 施設(ScatterplotLayer)だけに反応するツールチップ設定
        tooltip={
            "html": "<b>施設名:</b> {name}",
            "style": {"color": "white"}
        }
    ))

    st.success(f"表示完了: {selected_label} (n={n_rank})")

if __name__ == "__main__":
    main()