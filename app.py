import streamlit as st
import pandas as pd
import requests
from sklearn.cluster import DBSCAN
import io
import re
from datetime import datetime
from geopy.distance import geodesic, Point
from dotenv import load_dotenv
import os
import numpy as np

# タイトルの設定
st.title("あいのりタクシーアプリ___x1🚕👫")

# 出発地点の入力フォーム (デフォルトで渋谷のNHKの住所を設定)
start_address = st.text_input("出発地点を入力してください", placeholder="東京都渋谷区神南2-2-1 NHK放送センター")

# .envファイルを読み込む
load_dotenv()

# Google Maps APIキーの読み込み
api_key = os.getenv("MAP_KEY")

if not api_key:
    st.error("Google Maps APIキーが設定されていません。")

# ファイルアップロード
uploaded_file = st.file_uploader("Excelファイルをアップロードしてください", type=["xlsx"])

# APIアクセス制限
api_access_count = 0
max_api_access = 100

# Google Maps Geocoding APIを使用して住所から座標を取得する関数
def geocode_address(address, api_key):
    global api_access_count
    if api_access_count >= max_api_access:
        st.error("APIアクセス回数が100回を超えました。処理を停止します。")
        return None
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={api_key}"
    response = requests.get(url)
    api_access_count += 1
    st.write(f"{api_access_count}回目のAPIアクセス: {address}")
    
    if response.status_code == 200:
        data = response.json()
        if data['results']:
            location = data['results'][0]['geometry']['location']
            return (location['lat'], location['lng'])  # 緯度・経度を返す
        else:
            st.error(f"住所が見つかりませんでした: {address}")
            return None
    else:
        st.error(f"APIリクエストに失敗しました。ステータスコード: {response.status_code}")
        return None

# タクシー料金計算の関数
def calculate_taxi_fare(distance_km):
    base_fare = 500
    additional_fare = 100
    additional_distance = max(0, distance_km - 1.096)
    additional_units = additional_distance / 0.255
    taxi_fee = base_fare + int(additional_units) * additional_fare
    taxi_fee_midnight = taxi_fee * 1.2
    return round(taxi_fee), round(taxi_fee_midnight)

# クラスタリングのための距離行列を作成
def create_clusters(people, coords):
    st.write("距離行列の計算")
    dist_matrix = np.array([
        [
            geodesic(Point(c1), Point(c2)).km if c1 and c2 else float('inf')
            for c2 in coords
        ] for c1 in coords
    ])
    
    dbscan = DBSCAN(eps=2, min_samples=2, metric="precomputed")
    clusters = dbscan.fit_predict(dist_matrix)
    return clusters

# 住所の座標が不明な場合はデフォルト住所の座標を使用する関数
def get_start_coords(start_address, api_key):
    return geocode_address(start_address, api_key)

if uploaded_file and start_address and api_key:
    st.write("出発地点の住所を取得")
    start_coords = get_start_coords(start_address, api_key)

    # Excelファイルの読み込み
    st.write("Excelファイルの読み込み")
    df = pd.read_excel(uploaded_file)

    # プログレスバーの設定
    st.write("プログレスバーの設定")
    progress_bar = st.progress(0)
    total_steps = len(df)
    current_step = 0

    st.write("Excelファイルから住所データを取得して処理")
    people = []
    coords = []  # 座標リスト
    invalid_addresses = []  # 無効な住所リスト
    for index, row in df.iterrows():
        person = {
            "name": row["Name"],  # "Name"列から取得
            "address": row["Address"]  # "Address"列から取得
        }
        st.write(f"データ: {person['name']} - {person['address']}")
        people.append(person)

        # 住所の座標を取得
        location = geocode_address(person["address"], api_key)
        if location:
            coords.append(location)  # 緯度・経度をcoordsリストに追加
        else:
            coords.append(None)  # 座標が取得できなかった場合はNone
            invalid_addresses.append(person)  # 無効な住所リストに追加
        current_step += 1
        progress_bar.progress(current_step / total_steps)

    if len(people) < 1:
        st.error("十分な住所データが取得できませんでした。")
    else:
        # 無効な住所を除いてクラスタリング実行
        valid_people = [person for person, coord in zip(people, coords) if coord is not None]
        valid_coords = [coord for coord in coords if coord is not None]
        clusters = create_clusters(valid_people, valid_coords)
        
        taxi_groups = {}
        for i, cluster_id in enumerate(clusters):
            if cluster_id != -1:
                if cluster_id not in taxi_groups:
                    taxi_groups[cluster_id] = []
                taxi_groups[cluster_id].append(valid_people[i])

        # グループを3人ずつに分割して表示
        result_data = []
        for cluster_id, group in taxi_groups.items():
            for i in range(0, len(group), 3):
                sub_group = group[i:i+3]
                taxi_group = f"Taxi {cluster_id + 1}"
                for person in sub_group:
                    distance = geodesic(start_coords, geocode_address(person["address"], api_key)).km
                    taxi_fee, taxi_fee_midnight = calculate_taxi_fare(distance)
                    st.write(f"{person['name']} ({taxi_group}) のタクシー料金: {taxi_fee}円, 深夜料金: {taxi_fee_midnight if taxi_fee_midnight else 'N/A'}")
                    result_data.append({
                        "Taxi": taxi_group,
                        "Name": person['name'],
                        "Address": person['address'],
                        "Taxi Fee (Normal)": f"{taxi_fee}円",
                        "Taxi Fee (Midnight)": f"{taxi_fee_midnight}円" if taxi_fee_midnight else "N/A"
                    })

        # 無効な住所を結果の最後に追加
        for person in invalid_addresses:
            st.write(f"無効な住所: {person['name']} - {person['address']}")
            result_data.append({
                "Taxi": "N/A",
                "Name": person['name'],
                "Address": person['address'],
                "Taxi Fee (Normal)": "N/A",
                "Taxi Fee (Midnight)": "N/A"
            })

        # エクセルファイルに出力
        if st.button("結果をエクセルファイルとしてダウンロード"):
            result_df = pd.DataFrame(result_data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                result_df.to_excel(writer, index=False, sheet_name="Taxis")
            st.download_button(
                label="Download Excel",
                data=output.getvalue(),
                file_name="taxi_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
