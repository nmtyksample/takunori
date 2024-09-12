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
st.title("あいのりタクシーアプリ_タクとも19🚕👫")

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
        current_time = datetime.now
