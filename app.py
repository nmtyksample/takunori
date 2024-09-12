import streamlit as st
import pandas as pd
from geopy.distance import geodesic
import numpy as np
from sklearn.cluster import DBSCAN
import io
import requests
import urllib
import re
from datetime import datetime

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

# タクシー料金計算の関数
def calculate_taxi_fare(distance_km, current_time=None):
    # タクシー料金の計算 (東京の例: 初乗り料金430円、以降の加算料金)
    base_fare = 430  # 初乗り料金 (1.052kmまで)
    additional_fare = 80  # 加算料金 (237mごとに80円)
    additional_distance = max(0, distance_km - 1.052)  # 初乗りを超えた距離
    additional_units = additional_distance / 0.237  # 237mごと
    taxi_fee = base_fare + int(additional_units) * additional_fare  # 通常料金

    # 深夜料金の計算 (22:00〜5:00の間は20%増し)
    taxi_fee_midnight = taxi_fee * 1.2

    # 現在時刻の取得または指定された時間を使用
    if current_time is None:
        current_time = datetime.now()

    # 深夜料金が適用される場合は深夜料金も返す
    if current_time.hour >= 22 or current_time.hour < 5:
        return round(taxi_fee), round(taxi_fee_midnight)  # 両方の料金を返す
    else:
        return round(taxi_fee), None  # 通常料金のみ返す（深夜料金は適用されない）

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
                groups[len(groups)] = [perso
