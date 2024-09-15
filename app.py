import streamlit as st
import pandas as pd
import requests
from sklearn.cluster import DBSCAN
from geopy.distance import geodesic
import io
import re
from datetime import datetime
from dotenv import load_dotenv
import os
import numpy as np

# タイトルの設定
st.title("あいのりタクシーアプリ_タクとも_api1🚕👫")

# 出発地点の入力フォーム (デフォルトで渋谷のNHKの住所を設定)
start_address = st.text_input("出発地点を入力してください", placeholder="東京都渋谷区神南2-2-1 NHK放送センター")

# .envファイルを読み込む
load_dotenv()

# Google Maps APIキーの読み込み
api_key = os.getenv("MAP_KEY")

if not api_key:
    st.error("Google Maps APIキーが設定されていません。")

# ファイルアップロード
uploaded_file = st.file_uploader("Excelファイル（1列目に名前、2列目に住所）をアップロードしてください", type=["xlsx"])

# Google Maps Directions APIを使用してルート距離を取得する関数
def get_route_distance(start, end, api_key):
    url = f"https://maps.googleapis.com/maps/api/directions/json?origin={start}&destination={end}&key={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data['routes']:
            # 距離を取得 (メートル単位)
            distance_meters = data['routes'][0]['legs'][0]['distance']['value']
            distance_km = distance_meters / 1000  # キロメートルに変換
            return distance_km
        else:
            st.write(f"ルートが見つかりませんでした: {start} から {end}")
            return None
    else:
        st.write(f"APIリクエストに失敗しました。ステータスコード: {response.status_code}")
        return None

# タクシー料金計算の関数
def calculate_taxi_fare(distance_km, current_time=None):
    base_fare = 500  # 初乗り料金 (1.096kmまで)
    additional_fare = 100  # 加算料金 (255mごとに100円)
    additional_distance = max(0, distance_km - 1.096)  # 初乗りを超えた距離
    additional_units = additional_distance / 0.255  # 255mごと
    taxi_fee = base_fare + int(additional_units) * additional_fare  # 通常料金

    taxi_fee_midnight = taxi_fee * 1.2  # 深夜料金 (22:00〜5:00)

    return round(taxi_fee), round(taxi_fee_midnight)

# 住所の座標が不明な場合はデフォルト住所の座標を使用する関数
def get_start_coords(start_address):
    return start_address  # Google Maps APIを使用するので、座標ではなく住所を返す

if uploaded_file and start_address and api_key:
    # 出発地点の住所を取得
    start_coords = get_start_coords(start_address)

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
        people.append(person)

        # プログレスバーの更新
        current_step += 1
        progress_bar.progress(current_step / total_steps)

    if len(people) < 1:
        st.error("十分な住所データが取得できませんでした。")
    else:
        # ルート距離を取得し、各人の座標をリストに追加
        people_with_coords = []
        for person in people:
            distance = get_route_distance(start_coords, person["address"], api_key)
            if distance is not None:
                people_with_coords.append((person, distance))
            else:
                st.write(f"{person['name']}の距離を計算できませんでした。")
        
        if len(people_with_coords) < 2:
            st.error("十分な住所データが取得できませんでした。")
        else:
            # 座標のリストを作成
            coords = [get_route_distance(start_coords, p["address"], api_key) for p, _ in people_with_coords]
            
            # 距離行列を計算 (DBSCANクラスタリング用)
            dist_matrix = np.array([[geodesic(c1, c2).km for c2 in coords] for c1 in coords])

            # DBSCANでクラスタリング
            epsilon = 2  # 2km以内の点を同じクラスタと見なす
            dbscan = DBSCAN(eps=epsilon, min_samples=2, metric="precomputed")
            clusters = dbscan.fit_predict(dist_matrix)

            # グループ分け
            groups = {}
            for idx, cluster_id in enumerate(clusters):
                if cluster_id != -1:  # -1はノイズ
                    if cluster_id not in groups:
                        groups[cluster_id] = []
                    groups[cluster_id].append(people_with_coords[idx])

            # タクシーに割り当てる（最大3人まで）
            taxis = []
            for group in groups.values():
                for i in range(0, len(group), 3):
                    taxis.append(group[i:i+3])  # 3人ごとにタクシーに割り当て

            # 結果を表示
            result_data = []
            for i, taxi in enumerate(taxis):
                for passenger, distance in taxi:
                    taxi_fee, taxi_fee_midnight = calculate_taxi_fare(distance)
                    st.write(f"{passenger['name']}のタクシー料金: {taxi_fee}円, 深夜料金: {taxi_fee_midnight if taxi_fee_midnight else 'N/A'}")
                    result_data.append({
                        "Taxi": i + 1,
                        "Name": passenger['name'],
                        "Address": passenger['address'],
                        "Taxi Fee (Normal)": f"{taxi_fee}円",
                        "Taxi Fee (Midnight)": f"{taxi_fee_midnight}円" if taxi_fee_midnight else "N/A"
                    })

            # 結果をエクセルファイルとして出力
            if st.button("結果をエクセルファイルとしてダウンロード"):
                result_df = pd.DataFrame(result_data)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    result_df.to_excel(writer, index=False, sheet_name='Taxis')
                st.download_button(label="Download Excel", data=output.getvalue(), file_name="taxi_results.xlsx")
