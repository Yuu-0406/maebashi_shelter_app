import osmnx as ox
import pandas as pd
import folium
import random
import os
import pickle

# --- 設定 ---
CSV_FILE = "emergency_shelter_maebashi.csv"
GRAPH_CACHE = "maebashi_graph.graphml"
MAP_SAVE_DIR = "static_maps" # HTML地図の保存先
RESULT_CACHE_DIR = "cache_results"

def generate_all_maps():
    if not os.path.exists(MAP_SAVE_DIR): os.makedirs(MAP_SAVE_DIR)
    
    print("🚀 地図の全パターン生成を開始します...")
    G = ox.load_graphml(GRAPH_CACHE)
    
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
    except:
        df = pd.read_csv(CSV_FILE, encoding='cp932')

    ST_COLS = {
        "洪水": "flood", "崖崩れ,土石流及び地滑り": "landslides_debrisflow_medslides",
        "高潮": "storm_surge", "地震": "earthquake", "津波": "tsunami",
        "大規模な火事": "largescale_fire", "内水氾濫": "inlandflooding", "火山現象": "volcanic_phenomena"
    }

    for label, col in ST_COLS.items():
        cache_path = os.path.join(RESULT_CACHE_DIR, f"full_ranks_{col}.pkl")
        if not os.path.exists(cache_path):
            print(f"⚠️ キャッシュがないため {label} をスキップします。")
            continue
            
        with open(cache_path, 'rb') as f:
            node_rankings = pickle.load(f)
        
        active_shelters = df[df[col] == True].copy()
        max_n = len(active_shelters)
        
        # 避難所の色を固定（IDベース）
        random.seed(42)
        color_map = {sid: "#%06x" % random.randint(0, 0xFFFFFF) for sid in active_shelters.index}

        for n in range(1, max_n + 1):
            file_name = f"map_{col}_n{n}.html"
            save_path = os.path.join(MAP_SAVE_DIR, file_name)
            
            if os.path.exists(save_path): continue # すでに作成済みならスキップ

            # 地図作成
            m = folium.Map(location=[36.3895, 139.0634], zoom_start=13, tiles="cartodbpositron")
            
            # 道路網の描画
            for u, v, data in G.edges(data=True):
                ranks = node_rankings.get(u, [])
                if not ranks or len(ranks) < n: continue
                owner_id = ranks[n-1]
                color = color_map.get(owner_id, "#888888")
                points = [(G.nodes[u]['y'], G.nodes[u]['x']), (G.nodes[v]['y'], G.nodes[v]['x'])]
                folium.PolyLine(points, color=color, weight=3, opacity=0.7).add_to(m)

            # 施設の描画
            for idx, row in active_shelters.iterrows():
                folium.CircleMarker(
                    location=[row['lat'], row['lon']],
                    radius=6, color="black", weight=1,
                    fill=True, fill_color=color_map[idx], fill_opacity=1.0,
                    popup=row['name']
                ).add_to(m)

            m.save(save_path)
            print(f"✅ 保存完了: {label} n={n}")

    print("\n" + "="*30)
    print("✨ すべての計算と地図生成が完了しました！ ✨")
    print("アプリ(UI.py)を起動して確認してください。")
    print("="*30)

if __name__ == "__main__":
    generate_all_maps()