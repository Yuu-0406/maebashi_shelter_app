import pandas as pd
import pickle
import os

CSV_FILE = "emergency_shelter_maebashi.csv"
CACHE_DIR = "cache_results"

# --- CSV読み込み（UIコードと同じ方式） ---
try:
    df = pd.read_csv(CSV_FILE, encoding="utf-8")
except UnicodeDecodeError:
    df = pd.read_csv(CSV_FILE, encoding="cp932")

# --- ベースとなるランキング ---
with open(os.path.join(CACHE_DIR, "full_ranks_earthquake.pkl"), "rb") as f:
    base_ranks = pickle.load(f)

missing_disasters = [
    "storm_surge",
    "tsunami",
    "inlandflooding",
    "volcanic_phenomena"
]

for disaster in missing_disasters:
    active_ids = set(df.index[df[disaster] == True])

    disaster_ranks = {}
    for node, ranks in base_ranks.items():
        disaster_ranks[node] = [sid for sid in ranks if sid in active_ids]

    out_path = os.path.join(
        CACHE_DIR,
        f"full_ranks_{disaster}.pkl"
    )

    with open(out_path, "wb") as f:
        pickle.dump(disaster_ranks, f)

    print(f"{out_path} を作成しました")
