import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from geopy.distance import geodesic
import numpy as np
from sklearn.cluster import DBSCAN
import time

# タイトルの設定
st.title("あいのりタクシーアプリ -たくのり- ")

# ファイルアップロード
uploaded_file = st.file_uploader("名前と住所が記載されたExcelファイルをアップロードしてください", type=["xlsx"])

if uploaded_file:
    # Excelファイルの読み込み
    df = pd.read_excel(uploaded_file)
    
    # データの表示
    st.write("アップロードされたデータ:")
    st.write(df)
    
    # 欠損値や不要な空白を処理
    df = df.dropna(subset=['名前', '住所'])  # 名前と住所が欠損している行を削除
    df['住所'] = df['住所'].str.strip()  # 住所の空白を除去
    
    # データの表示
    st.write("クリーニングされたデータ:")
    st.write(df)

    if st.button("結果を表示"):
        geolocator = Nominatim(user_agent="taxi_allocation")

        def geocode_with_retry(address, retries=5, delay=3):
            for attempt in range(retries):
                try:
                    return geolocator.geocode(address)
                except GeocoderTimedOut:
                    if attempt < retries - 1:
                        st.write(f"Timeout occurred. Retrying ({attempt + 1}/{retries})...")
                        time.sleep(delay)
                    else:
                        st.write(f"Failed to geocode address after {retries} attempts: {address}")
                        return None

        # 住所のジオコーディング
        coords = []
        for address in df['住所']:
            location = geocode_with_retry(address)
            if location:
                coords.append((location.latitude, location.longitude))
            else:
                coords.append((None, None))

        # デバッグ: 取得した座標を表示
        st.write("取得した座標:")
        st.write(coords)

        df['Latitude'] = [coord[0] for coord in coords]
        df['Longitude'] = [coord[1] for coord in coords]

        # 緯度経度の取得に失敗した行を除外
        df = df.dropna(subset=['Latitude', 'Longitude'])

        # 有効なデータがあるか確認
        if df.empty:
            st.error("有効な住所がありませんでした。すべての住所がジオコーディングに失敗しました。")
        else:
            # 距離行列の作成
            coords = df[['Latitude', 'Longitude']].values

            if len(coords) < 2:
                st.error("十分な座標データがありません。クラスタリングには少なくとも2つの有効な座標が必要です。")
            else:
                dist_matrix = np.array([[geodesic(coord1, coord2).km for coord2 in coords] for coord1 in coords])

                # デバッグ: 距離行列を表示
                st.write("距離行列:")
                st.write(dist_matrix)

                # DBSCANでクラスタリング
                if dist_matrix.size > 0:
                    epsilon = 2  # 2km以内の点を同じクラスタと見なす
                    dbscan = DBSCAN(eps=epsilon, min_samples=2, metric="precomputed")
                    clusters = dbscan.fit_predict(dist_matrix)

                    df['Cluster'] = clusters

                    # 結果の表示
                    st.write("クラスタリング結果:")
                    for cluster_id in df['Cluster'].unique():
                        cluster_group = df[df['Cluster'] == cluster_id]
                        st.write(f"**クラスタ {cluster_id}**")
                        st.write(cluster_group[['名前', '住所']])
                    
                    # 結果をエクセルファイルとしてダウンロード
                    output = st.button("結果をエクセルファイルとしてダウンロード")
                    if output:
                        output_df = df[['名前', '住所', 'Cluster']]
                        output_df.to_excel("クラスタリング結果.xlsx", index=False)
                        st.write("結果をエクセルファイルとして保存しました。")
                else:
                    st.error("距離行列が空です。クラスタリングを実行できませんでした。")
