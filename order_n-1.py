import streamlit as st
import osmnx as ox
import pandas as pd
import folium
from streamlit_folium import st_folium
import random
import os
import pickle
import networkx as nx

# --- 1. パスワード認証機能 ---
APP_PASSWORD = "114" 

def check_password():
    if "password_correct" not in st.session_state:
        st.title("前橋市 避難所解析システム")
        st.subheader("🔒 ログインが必要です")
        st.text_input("パスワードを入力してください", type="password", key="pwd_input")
        if st.button("ログイン"):
            if st.session_state.pwd_input == APP_PASSWORD:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("パスワードが正しくありません")
        return False
    return True

# --- 2. 高速化のための計算ロジック (全順位一括計算) ---
def calculate_all_ranks_voronoi(G, shelters_df):
    """道路上の各地点から、全避難所への『近い順リスト』を作成する"""
    shelter_nodes = ox.nearest_nodes(G, shelters_df['lon'], shelters_df['lat'])
    node_to_shelter_id = dict(zip(shelter_nodes, shelters_df.index))
    
    node_rankings = {node: [] for node in G.nodes()}
    unique_shelter_nodes = list(set(shelter_nodes))
    
    prog_bar = st.progress(0, text="全順位の距離計算中...")
    for i, s_node in enumerate(unique_shelter_nodes):
        lengths = nx.single_source_dijkstra_path_length(G, s_node, weight='length')
        for node, dist in lengths.items():
            node_rankings[node].append((dist, node_to_shelter_id[s_node]))
        prog_bar.progress((i + 1) / len(unique_shelter_nodes))
    
    # 距離順にソートしてIDだけのリストに変換
    for node in node_rankings:
        node_rankings[node].sort()
        node_rankings[node] = [val[1] for val in node_rankings[node]]
    
    prog_bar.empty()
    return node_rankings

# --- 3. メインアプリ設定 ---
CSV_FILE = "emergency_shelter_maebashi.csv"
GRAPH_CACHE = "maebashi_graph.graphml"
RESULT_CACHE_DIR = "cache_results"

@st.cache_resource
def get_maebashi_graph():
    if os.path.exists(GRAPH_CACHE):
        return ox.load_graphml(GRAPH_CACHE)
    G = ox.graph_from_place("Maebashi, Gunma, Japan", network_type='walk')
    ox.save_graphml(G, GRAPH_CACHE)
    return G

def main():
    if not check_password(): st.stop()

    # データの読み込み
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
    except:
        df = pd.read_csv(CSV_FILE, encoding='cp932')

    # サイドバー設定
    st.sidebar.header("1. 解析条件")
    ST_COLS = {
        "洪水": "flood", "崖崩れ,土石流及び地滑り": "landslides_debrisflow_medslides",
        "高潮": "storm_surge", "地震": "earthquake", "津波": "tsunami",
        "大規模な火事": "largescale_fire", "内水氾濫": "inlandflooding", "火山現象": "volcanic_phenomena"
    }
    selected_label = st.sidebar.selectbox("災害種類", list(ST_COLS.keys()))
    disaster_col = ST_COLS[selected_label]
    
    active_shelters = df[df[disaster_col] == True].copy()
    max_n = len(active_shelters)
    
    if max_n == 0:
        st.error("利用可能な施設がありません")
        st.stop()

    n_rank = st.sidebar.number_input(f"何番目に近い施設 (n) [1〜{max_n}]", 1, max_n, 1)

    # 強調表示の制御
    if "target_name" not in st.session_state:
        st.session_state.target_name = "なし"

    st.sidebar.header("2. 表示・強調設定")
    selected_shelter = st.sidebar.selectbox(
        "施設名から選んで強調", ["なし"] + active_shelters['name'].tolist(),
        index=(["なし"] + active_shelters['name'].tolist()).index(st.session_state.target_name)
    )
    st.session_state.target_name = selected_shelter

    # 解析実行ボタン
    if st.sidebar.button("解析実行/更新"):
        # ボタン押下時は特になにもせず再描画を促す
        pass

    # --- データの準備 ---
    G = get_maebashi_graph()
    cache_path = os.path.join(RESULT_CACHE_DIR, f"full_ranks_{disaster_col}.pkl")

    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            node_rankings = pickle.load(f)
    else:
        with st.spinner("新規災害パターンの全順位を計算中... (数分かかります)"):
            node_rankings = calculate_all_ranks_voronoi(G, active_shelters)
            with open(cache_path, 'wb') as f:
                pickle.dump(node_rankings, f)
            st.success("全順位データの計算・保存が完了しました！")

    # --- 地図の作成 ---
    m = folium.Map(location=[36.3895, 139.0634], zoom_start=13, tiles="cartodbpositron")
    
    # 色の設定 (施設IDと領域色を一致させる)
    random.seed(42)
    color_map = {sid: "#%06x" % random.randint(0, 0xFFFFFF) for sid in active_shelters.index}
    
    target_id = None
    if st.session_state.target_name != "なし":
        target_id = active_shelters[active_shelters['name'] == st.session_state.target_name].index[0]

    # 道路網の描画
    for u, v, data in G.edges(data=True):
        # n番目の持ち主を特定
        ranks = node_rankings.get(u, [])
        owner_id = ranks[n_rank-1] if len(ranks) >= n_rank else None
        
        color = color_map.get(owner_id, "#888888")
        weight, opacity = (8, 1.0) if owner_id == target_id and target_id is not None else (3, 0.6)
        if target_id is not None and owner_id != target_id: opacity = 0.1 # 強調時は他を薄く

        points = [(lat, lon) for lon, lat in (data['geometry'].coords if 'geometry' in data else [(G.nodes[u]['x'], G.nodes[u]['y']), (G.nodes[v]['x'], G.nodes[v]['y'])])]
        # x, y が逆転している場合があるため修正
        if not 'geometry' in data: points = [(G.nodes[u]['y'], G.nodes[u]['x']), (G.nodes[v]['y'], G.nodes[v]['x'])]
        
        folium.PolyLine(points, color=color, weight=weight, opacity=opacity).add_to(m)

    # 施設の描画
    for idx, row in active_shelters.iterrows():
        is_target = (idx == target_id)
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=12 if is_target else 6,
            color="black", weight=1,
            fill=True, fill_color=color_map[idx], # 領域の色と一致
            fill_opacity=1.0,
            popup=f"{row['name']} (順位:{n_rank})",
            tooltip=row['name']
        ).add_to(m)

    # 地図の表示とクリック検知
    out = st_folium(m, width=1200, height=700, key="main_map")

    # 地図クリック時の連動 (施設クリック)
    if out.get("last_object_clicked_popup"):
        clicked_name = out["last_object_clicked_popup"].split(" (順位:")[0]
        if st.session_state.target_name != clicked_name:
            st.session_state.target_name = clicked_name
            st.rerun()

if __name__ == "__main__":
    if not os.path.exists(RESULT_CACHE_DIR): os.makedirs(RESULT_CACHE_DIR)
    main()