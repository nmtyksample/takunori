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
st.title("あいのりタクシーアプリ_タクとも22🚕👫")

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
            st.write(f"{address} の座標: {coordinates}")  # デバッグ出力
            return coordinates  # GSIは経度、緯度の順で返すことが多い
        else:
            st.write(f"住所 '{address}' が見つかりませんでした。")
            return None
    else:
        st.write(f"APIリクエストに失敗しました。ステータスコード: {response.status_code}")
        return None

# タクシー料金計算の関数
def calculate_taxi_fare(distance_km, current_time=None):
    base_fare = 430  # 初乗り料金 (1.052kmまで)
    additional_fare = 80  # 加算料金 (237mごとに80円)
    additional_distance = max(0, distance_km - 1.052)  # 初乗りを超えた距離
    additional_units = additional_distance / 0.237  # 237mごと
    taxi_fee = base_fare + int(additional_units) * additional_fare  # 通常料金

    taxi_fee_midnight = taxi_fee * 1.2  # 深夜料金 (22:00〜5:00)

    if current_time is None:
        current_time = datetime.now()

    if current_time.hour >= 22 or current_time.hour < 5:
        return round(taxi_fee), round(taxi_fee_midnight)
    else:
        return round(taxi_fee), None

# 座標が有効かどうかを確認する関数
def is_valid_coordinates(coords):
    if coords is None:
        return False
    # GSIから返される座標は経度、緯度の順なので、それを考慮して変換
    longitude, latitude = coords  # GSIの座標は経度、緯度の順で返される
    # latitude, longitude = coords  # GSIの座標は経度、緯度の順で返される
    st.write(f"Checking coordinates: 緯度: {latitude}, 経度: {longitude}")  # デバッグ出力
    # 緯度が-90から90、経度が-180から180の範囲内であることを確認
    return -90 <= latitude <= 90 and -180 <= longitude <= 180

# 住所の座標が不明な場合はデフォルト住所の座標を使用する関数
def get_start_coords(start_address):
    coords = geocode_with_retry(start_address)
    if not is_valid_coordinates(coords):
        st.write("入力された住所の座標が見つかりませんでした。デフォルトの座標を使用します。")
        # デフォルトの座標（東京都渋谷区神南2-2-1）を取得
        default_address = "東京都渋谷区神南2-2-1"
        coords = geocode_with_retry(default_address)
        if not is_valid_coordinates(coords):
            st.error("デフォルトの座標も見つかりません。設定値を見直してください。")
            return None
    return coords

if uploaded_file and start_address:
    # 出発地点の緯度経度を取得
    start_coords = get_start_coords(start_address)
    if start_coords is None:
        st.stop()  # 出発地点の座標が取得できない場合、処理を停止

    st.write(f"出発地点の座標: {start_coords}")  # デバッグ出力

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
        if is_valid_coordinates(location):
            person["coords"] = (location[1], location[0])  # 経度、緯度を緯度、経度に変換
        else:
            st.write(f"Error: Could not geocode address for {person['name']} - {person['address']}")
            person["coords"] = None  # 座標が見つからなかった場合
        people.append(person)

        # プログレスバーの更新
        current_step += 1
        progress_bar.progress(current_step / total_steps)

    # 座標が取得できた人のみを対象にする
    people_with_coords = [person for person in people if is_valid_coordinates(person["coords"])]
    people_without_coords = [person for person in people if not is_valid_coordinates(person["coords"])]

    # 座標のリストを作成
    coords = [person["coords"] for person in people_with_coords]

    if len(coords) < 2 and len(people_without_coords) == 0:
        st.error("十分な住所データが取得できませんでした。")
    else:
        # 距離行列を計算
        if len(coords) >= 2:
            dist_matrix = np.array([[geodesic(c1, c2).km for c2 in coords] for c1 in coords])

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
                # 座標が有効か確認
                if is_valid_coordinates(passenger["coords"]):
                    try:
                        distance = geodesic(start_coords, passenger["coords"]).km
                        st.write(f"{passenger['name']}との距離: {distance} km")  # デバッグ出力
                        taxi_fee, taxi_fee_midnight = calculate_taxi_fare(distance)
                        st.write(f"{passenger['name']}のタクシー料金: {taxi_fee}円, 深夜料金: {taxi_fee_midnight if taxi_fee_midnight else 'N/A'}")  # デバッグ出力
                        if taxi_fee_midnight:
                            result_data.append({
                                "Taxi": i + 1,
                                "Name": passenger['name'],
                                "Address": passenger['address'],
                                "Taxi Fee (Normal)": f"{taxi_fee}円",
                                "Taxi Fee (Midnight)": f"{taxi_fee_midnight}円"
                            })
                        else:
                            result_data.append({
                                "Taxi": i + 1,
                                "Name": passenger['name'],
                                "Address": passenger['address'],
                                "Taxi Fee (Normal)": f"{taxi_fee}円",
                                "Taxi Fee (Midnight)": "N/A"
                            })
                    except Exception as e:
                        st.write(f"Error calculating distance or fare for {passenger['name']}: {e}")  # デバッグ用エラーログ
                        result_data.append({
                            "Taxi": i + 1,
                            "Name": passenger['name'],
                            "Address": passenger['address'],
                            "Taxi Fee (Normal)": "N/A",
                            "Taxi Fee (Midnight)": "N/A"
                        })
                else:
                    st.write(f"Invalid coordinates for {passenger['name']}: {passenger['coords']}")  # デバッグ出力
                    result_data.append({
                        "Taxi": i + 1,
                        "Name": passenger['name'],
                        "Address": passenger['address'],
                        "Taxi Fee (Normal)": "N/A",
                        "Taxi Fee (Midnight)": "N/A"
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
