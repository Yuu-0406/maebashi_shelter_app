import streamlit as st
import pandas as pd
import pydeck as pdk
import os
import pickle
import osmnx as ox
import random
from collections import Counter

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

# --- 設定 ---
CSV_FILE = "emergency_shelter_maebashi.csv"
GRAPH_CACHE = "maebashi_graph.graphml"
RESULT_CACHE_DIR = "cache_results"

@st.cache_resource
def load_graph_edges():
    if not os.path.exists(GRAPH_CACHE):
        st.error(f"グラフファイル {GRAPH_CACHE} が見つかりません。")
        return []
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

    st.title("前橋市 避難所【ネットワークボロノイ図解析】")

    # --- データの読み込み ---
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
    except:
        df = pd.read_csv(CSV_FILE, encoding='cp932')

    # --- サイドバー設定 ---
    st.sidebar.header("解析条件")
    ST_COLS = {
        "洪水": "flood", "崖崩れ、土石流及び地滑り": "landslides_debrisflow_mudslides",
        "高潮": "storm_surge", "地震": "earthquake", "津波": "tsunami",
        "大規模な火事": "largescale_fire", "内水氾濫": "inlandflooding", "火山現象": "volcanic_phenomena"
    }
    selected_label = st.sidebar.selectbox("災害種類", list(ST_COLS.keys()))
    disaster_col = ST_COLS[selected_label]
    
    # 災害種別でフィルタリング
    active_shelters_all = df[df[disaster_col] == True].copy()
    
    # 重複を削除（名前が同じ施設は一つに統合）
    active_shelters = active_shelters_all.drop_duplicates(subset=['name']).copy()
    # 判定用に、重複削除前のIDセットも保持
    active_ids_all = set(active_shelters_all.index) 
    
    max_n = len(active_shelters)
    
    if max_n == 0:
        st.sidebar.warning("この災害では利用可能な避難所がありません")
        st.info(f"【{selected_label}】に対応可能な避難所は0件です。")
        st.stop()

    n_rank = st.sidebar.number_input(
        f"何番目に近い施設(n)※最大{max_n}",
        min_value=1,
        max_value=max_n,
        value=1 
    )

    # --- 解析データの読み込み ---
    cache_path = os.path.join(RESULT_CACHE_DIR, f"full_ranks_{disaster_col}.pkl")
    if not os.path.exists(cache_path):
        cache_path = os.path.join(RESULT_CACHE_DIR, "full_ranks_all.pkl") 

    if not os.path.exists(cache_path):
        st.error("解析用データ(.pkl)が見つかりません。")
        return

    with st.spinner("ネットワーク解析を実行中..."):
        all_edges = load_graph_edges()
        with open(cache_path, 'rb') as f:
            node_rankings = pickle.load(f)
        
        # 名前ベースで色を固定
        random.seed(42)
        unique_names = active_shelters['name'].unique()
        name_to_color = {name: [random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)] 
                         for name in unique_names}

        path_data = []
        assigned_names_list = []

        for edge in all_edges:
            ranks = node_rankings.get(edge['u'], [])
            filtered_ranks = [sid for sid in ranks if sid in active_ids_all]
            
            if len(filtered_ranks) >= n_rank:
                owner_id = filtered_ranks[n_rank-1]
                owner_name = df.at[owner_id, 'name']
                
                path_data.append({
                    "path": edge['path'],
                    "color": name_to_color.get(owner_name, [200, 200, 200]),
                    "owner_name": owner_name
                })
                assigned_names_list.append(owner_name)

    # --- 統計データの作成（名前ベース） ---
    name_counts = Counter(assigned_names_list)
    summary_data = []
    for _, row in active_shelters.iterrows():
        summary_data.append({
            "避難所名": row['name'],
            "担当道路数": name_counts.get(row['name'], 0)
        })

    # 【重要】ソート順を固定
    # 第1優先：道路数（多い順）、第2優先：避難所名（あいうえお順）
    res_df = pd.DataFrame(summary_data).sort_values(
        by=["担当道路数", "避難所名"], 
        ascending=[False, True]
    )

    # インデックスを 1, 2, 3... に振り直して「順位」として見せる
    res_df = res_df.reset_index(drop=True)
    res_df.index = res_df.index + 1

    num_assigned_unique = len([name for name, count in name_counts.items() if count > 0])

    # --- メトリクス表示 ---
    col1, col2 = st.columns(2)
    col1.metric("有効な施設総数", f"{max_n} 箇所")
    col2.metric("道路をカバー中の施設数", f"{num_assigned_unique} 箇所")

    # --- Pydeck描画 ---
    view_state = pdk.ViewState(latitude=36.3895, longitude=139.0634, zoom=12)
    
    path_layer = pdk.Layer(
        "PathLayer", path_data, get_path="path", get_color="color",
        width_min_pixels=2, pickable=False,
    )

    shelter_layer_data = [{
        "position": [row['lon'], row['lat']],
        "name": row['name'],
        "fill_color": name_to_color[row['name']]
    } for _, row in active_shelters.iterrows()]

    shelter_layer = pdk.Layer(
        "ScatterplotLayer", shelter_layer_data, get_position="position",
        get_fill_color="fill_color", get_radius=100, radius_min_pixels=8, pickable=True,
    )

    st.pydeck_chart(pdk.Deck(
        layers=[path_layer, shelter_layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/light-v9",
        tooltip={"html": "<b>施設名:</b> {name}"}
    ))

    # --- 結果表示 ---
    st.subheader("避難所別の担当道路数ランキング")
    st.dataframe(res_df, use_container_width=True)

    # 担当0の警告
    zero_shelters = res_df[res_df["担当道路数"] == 0]
    if not zero_shelters.empty:
        st.warning(f"以下の施設は、n={n_rank} の条件で担当エリアを持ちません：")
        st.write(", ".join(zero_shelters["避難所名"].tolist()))

if __name__ == "__main__":
    main()