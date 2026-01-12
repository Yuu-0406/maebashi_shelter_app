import osmnx as ox
import networkx as nx
import pandas as pd
import pickle
import os

# --- 設定 ---
CSV_FILE = "emergency_shelter_maebashi.csv"
GRAPH_CACHE = "maebashi_graph.graphml"  # 拡張子が .gz か確認してください
RESULT_CACHE_DIR = "cache_results1"

if not os.path.exists(RESULT_CACHE_DIR):
    os.makedirs(RESULT_CACHE_DIR)

def generate_rankings():
    print("🚀 解析を開始します。これには時間がかかります...")
    G = ox.load_graphml(GRAPH_CACHE)
    # 重みとして距離(length)を使用
    
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
    except:
        df = pd.read_csv(CSV_FILE, encoding='cp932')

    # 解析したい災害列リスト（すべて網羅）
    ST_COLS = {
        "flood": "flood",
        "landslides_debrisflow_mudslides": "landslides_debrisflow_mudslides", # mudに統一
        "storm_surge": "storm_surge",
        "earthquake": "earthquake",
        "tsunami": "tsunami",
        "largescale_fire": "largescale_fire",
        "inlandflooding": "inlandflooding",
        "volcanic_phenomena": "volcanic_phenomena"
    }

    # 全ノードのリスト
    nodes = list(G.nodes())

    for label, col in ST_COLS.items():
        save_path = os.path.join(RESULT_CACHE_DIR, f"full_ranks_{col}.pkl")
        print(f"--- {col} の解析中 ---")

        # その災害で利用可能な避難所を抽出
        active_shelters = df[df[col] == True]
        if active_shelters.empty:
            print(f"⚠️ {col} に該当する避難所がないためスキップします。")
            continue

        # 避難所に最も近い道路ノードを取得
        target_nodes = ox.nearest_nodes(G, active_shelters['lon'], active_shelters['lat'])
        # 避難所IDとノードIDの対応マップ
        node_to_shelter_id = {node: sid for node, sid in zip(target_nodes, active_shelters.index)}

        node_rankings = {}
        
        # 多対多の最短経路計算（各ノードから全避難所への距離順を計算）
        for node in nodes:
            # 各避難所ノードへの距離を計算し、近い順にソートして保持
            distances = {}
            for target_node, sid in node_to_shelter_id.items():
                try:
                    dist = nx.shortest_path_length(G, node, target_node, weight='length')
                    distances[sid] = dist
                except nx.NetworkXNoPath:
                    continue
            
            # 距離が近い順に避難所IDを並べ替えて保存
            sorted_shelters = sorted(distances, key=distances.get)
            node_rankings[node] = sorted_shelters

        with open(save_path, 'wb') as f:
            pickle.dump(node_rankings, f)
        print(f"✅ {save_path} を作成しました。")

if __name__ == "__main__":
    generate_rankings()