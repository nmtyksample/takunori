import streamlit as st
import pandas as pd
from geopy.distance import geodesic
import numpy as np
from sklearn.cluster import DBSCAN
import io
import requests
import urllib
import re

# タイトルの設定
st.title("あいのりタクシーアプリ_タクとも🚕👫")

# 出発地点の入力フォーム (デフォルトで渋谷のNHKの住所を設定)
start_address = st.text_input("出発地点を入力してください", placeholder="東京都渋谷区神南2-2-1 NHK放送センター")

# ファイルアップロード
uploaded_file = st.file_uploader("Excelファイル（1列目に名前、2列目に住所）をアップロードしてください", type=["xlsx"])

# GSI APIを使用して緯度経度を取得する関数
def geocode_with_retry(address):
    makeUrl = "https://msearch.gsi.go.jp/address-search/AddressSearch?q="
    s_quote = urllib.parse.quote(address)
    response = requests.get(makeUrl + s_quote)
    if response.status_code == 200:
        data = response.json()
        if data:
            # 緯度経度を取得
            coordinates = data[0]["geometry"]["coordinates"]
            return coordinates  # GSIは経度、緯度の順で返すことが多い
        else:
            st.write(f"住所 '{address}' が見つかりませんでした。住所の表記が正しいか確認してください（例: '〇〇市〇〇区' の形式）。")
            return None, None
    else:
        st.write("APIリクエストに失敗しました。インターネット接続やAPIの状態を確認してください。")
        return None, None

if uploaded_file and start_address:
    # 出発地点の緯度経度を取得
    start_coords = geocode_with_retry(start_address)
    if not start_coords:
        st.error("出発地点の緯度経度が取得できませんでした。")
    else:
        # Excelファイルの読み込み
        df = pd.read_excel(uploaded_file)

        # プログレスバーの設定
        progress_bar = st.progress(0)
        total_steps = len(df)  # 全ステップ数はデータ行数
        current_step = 0

        # Excelファイルから住所データを取得して処理
        people = []
        for index, row in df.iterrows():
            person = {
                "name": row.iloc[0],  
                "address": row.iloc[1]  
            }
            location = geocode_with_retry(person["address"])
            if location:
                person["coords"] = (location[1], location[0])
            else:
                st.write(f"Error: Could not geocode address for {person['name']} - {person['address']}")
                person["coords"] = None  # 座標が見つからなかった場合
            people.append(person)

            # プログレスバーの更新
            current_step += 1
            progress_bar.progress(current_step / total_steps)

        # 座標が取得できた人のみを対象にする
        people_with_coords = [person for person in people if person["coords"]]
        people_without_coords = [person for person in people if person["coords"] is None]

        # 座標のリストを作成
        coords = [person["coords"] for person in people_with_coords]

        if len(coords) < 2 and len(people_without_coords) == 0:
            st.error("十分な住所データが取得できませんでした。")
        else:
            # 距離行列を計算
            if len(coords) >= 2:
                dist_matrix = np.array([[geodesic(coord1, coord2).km for coord2 in coords] for coord1 in coords])

                # DBSCANでクラスタリング
                epsilon = 2  # 2km以内の点を同じクラスタと見なす
                dbscan = DBSCAN(eps=epsilon, min_samples=2, metric="precomputed")
                clusters = dbscan.fit_predict(dist_matrix)

                # グループ分け
                groups = {}
                for idx, cluster_id in enumerate(clusters):
                    if cluster_id != -1:  # -1はノイズ（どのクラスタにも属さない）
                        if cluster_id not in groups:
                            groups[cluster_id] = []
                        groups[cluster_id].append(people_with_coords[idx])

                # 残ったノイズの処理（個別タクシー）
                noise = [people_with_coords[idx] for idx, cluster_id in enumerate(clusters) if cluster_id == -1]
                for person in noise:
                    groups[len(groups)] = [person]

            else:
                groups = {}  # 座標がない場合の処理

            # 住所が見つからなかった人は1人で1台のタクシーを使用
            for person in people_without_coords:
                groups[len(groups)] = [person]

            # タクシー割り当て
            taxis = []
            for group in groups.values():
                for i in range(0, len(group), 3):
                    taxis.append(group[i:i+3])  # 最大3人までのグループをタクシーに割り当て

            # 結果を表示
            result_data = []
            for i, taxi in enumerate(taxis):
                for passenger in taxi:
                    result_data.append({
                        "Taxi": i + 1,
                        "Name": passenger['name'],
                        "Address": passenger['address']
                    })

            # 住所から「区」や「町」を抽出する関数（どの地域でも対応）
            def extract_area(address):
                match = re.search(r'(\S+区|\S+町|\S+市)', address)
                if match:
                    return match.group(1)
                return None

            # 並び替えのロジックを追加
            for passenger in result_data:
                passenger["Area"] = extract_area(passenger["Address"])

            # Taxiごとに並び替え（「Taxi」->「Area」）
            result_data_sorted = sorted(result_data, key=lambda x: (x["Taxi"], x["Area"]))

            # 結果をエクセルファイルとして出力
            if st.button("結果をエクセルファイルとしてダウンロード"):
                result_df = pd.DataFrame(result_data_sorted)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    result_df.to_excel(writer, index=False, sheet_name='Taxis')
                st.download_button(label="Download Excel", data=output.getvalue(), file_name="taxi_results.xlsx")
