import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from googletrans import Translator
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.distance import geodesic
import numpy as np
from sklearn.cluster import DBSCAN
import time
import io

# タイトルの設定
st.title("あいのりタクシーアプリ4")

# ファイルアップロード
uploaded_file = st.file_uploader("名前と住所が記載されたExcelファイルをアップロードしてください", type=["xlsx"])

if uploaded_file:
    # Excelファイルの読み込み
    df = pd.read_excel(uploaded_file)
    st.write("アップロードされたデータ:")
    st.write(df)
    
    # Google Translate APIを使用して住所を英語に翻訳
    translator = Translator()

    def translate_address(address):
        translated = translator.translate(address, src='ja', dest='en')
        return translated.text

    # ジオコーダの設定
    geolocator = Nominatim(user_agent="taxi_allocation", timeout=10)  # タイムアウトを10秒に設定

    def geocode_with_retry(address, retries=5, delay=3):
        for attempt in range(retries):
            try:
                return geolocator.geocode(address)
            except (GeocoderTimedOut, GeocoderUnavailable) as e:
                if attempt < retries - 1:
                    print(f"Error: {e}. Retrying ({attempt + 1}/{retries})...")
                    time.sleep(delay)  # リトライ前に待機
                else:
                    print(f"Failed to geocode address after {retries} attempts: {address}")
                    return None

    # プログレスバーの設定
    progress_bar = st.progress(0)
    total_steps = len(df)  # 全ステップ数はデータ行数
    current_step = 0

    # Excelファイルから住所データを取得して処理
    people = []
    for index, row in df.iterrows():
        person = {
            "name": row["名前"],  # Excelの列名が"name"と仮定しています
            "address": row["住所"]  # Excelの列名が"address"と仮定しています
        }
        translated_address = translate_address(person["address"])
        location = geocode_with_retry(translated_address)
        if location:
            person["coords"] = (location.latitude, location.longitude)
        else:
            st.write(f"Error: Could not geocode address for {person['name']} - {translated_address}")
            person["coords"] = None  # 座標が見つからなかった場合
        people.append(person)

        # プログレスバーの更新
        current_step += 1
        progress_bar.progress(current_step / total_steps)

    # 座標が取得できた人のみを対象にする
    people_with_coords = [person for person in people if person["coords"]]

    # 座標のリストを作成
    coords = [person["coords"] for person in people_with_coords]

    if len(coords) < 2:
        st.error("十分な住所データが取得できませんでした。")
    else:
        # 距離行列を計算
        dist_matrix = np.array([[geodesic(coord1, coord2).km for coord2 in coords] for coord1 in coords])

        # DBSCANでクラスタリング
        epsilon = 3  # 3km以内の点を同じクラスタと見なす
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

        # タクシー割り当て
        taxis = []
        for group in groups.values():
            for i in range(0, len(group), 3):
                taxis.append(group[i:i+3])  # 最大3人までのグループをタクシーに割り当て

        # 結果を表示
        result_data = []
        for i, taxi in enumerate(taxis):
            st.write(f"Taxi {i + 1}:")
            for passenger in taxi:
                st.write(f"  {passenger['name']} - {passenger['address']}")
                result_data.append({
                    "Taxi": i + 1,
                    "Name": passenger['name'],
                    "Address": passenger['address']
                })

        # 結果をエクセルファイルとして出力
        if st.button("結果をエクセルファイルとしてダウンロード"):
            result_df = pd.DataFrame(result_data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                result_df.to_excel(writer, index=False, sheet_name='Taxis')
            st.download_button(label="Download Excel", data=output.getvalue(), file_name="taxi_results.xlsx")
