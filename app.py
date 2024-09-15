import streamlit as st
import pandas as pd
import requests
from sklearn.cluster import DBSCAN
import io
import re
from datetime import datetime

from dotenv import load_dotenv
import os

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

    # if current_time is None:
    #     current_time = datetime.now()

    return round(taxi_fee), round(taxi_fee_midnight)

    # if current_time.hour >= 22 or current_time.hour < 5:
    #     return round(taxi_fee), round(taxi_fee_midnight)
    # else:
    #     return round(taxi_fee), None

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
        # 結果を表示
        result_data = []
        for i, person in enumerate(people):
            distance = get_route_distance(start_coords, person["address"], api_key)
            if distance is not None:
                taxi_fee, taxi_fee_midnight = calculate_taxi_fare(distance)
                st.write(f"{person['name']}のタクシー料金: {taxi_fee}円, 深夜料金: {taxi_fee_midnight if taxi_fee_midnight else 'N/A'}")
                result_data.append({
                    "Taxi": i + 1,
                    "Name": person['name'],
                    "Address": person['address'],
                    "Taxi Fee (Normal)": f"{taxi_fee}円",
                    "Taxi Fee (Midnight)": f"{taxi_fee_midnight}円" if taxi_fee_midnight else "N/A"
                })
            else:
                st.write(f"{person['name']}の距離を計算できませんでした。")
                result_data.append({
                    "Taxi": i + 1,
                    "Name": person['name'],
                    "Address": person['address'],
                    "Taxi Fee (Normal)": "N/A",
                    "Taxi Fee (Midnight)": "N/A"
                })

        # 住所から「区」や「町」を抽出する関数
        def extract_area(address):
            match = re.search(r'(\S+区|\S+町|\S+市)', address)
            if match:
                return match.group(1)
            return None

        # 並び替えのロジックを追加
        for person in result_data:
            person["Area"] = extract_area(person["Address"])

        # Taxiごとに並び替え（「Taxi」->「Area」）
        result_data_sorted = sorted(result_data, key=lambda x: (x["Taxi"], x["Area"]))

        # 結果をエクセルファイルとして出力
        if st.button("結果をエクセルファイルとしてダウンロード"):
            result_df = pd.DataFrame(result_data_sorted)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                result_df.to_excel(writer, index=False, sheet_name='Taxis')
            st.download_button(label="Download Excel", data=output.getvalue(), file_name="taxi_results.xlsx")