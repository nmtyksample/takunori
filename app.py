import streamlit as st
import pandas as pd
import requests
from sklearn.cluster import DBSCAN
import io
from datetime import datetime
from geopy.distance import geodesic, Point
import os
import numpy as np
from googlemaps import convert

st.markdown(
    """
    <style>
    /* エラーメッセージのz-indexを上げる */
    .stAlert {
        z-index: 9999;
        position: relative;
    }

    /* プログレスバーのz-indexを下げる */
    .stProgress > div > div {
        z-index: 1;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# セッション状態で認証フラグを管理
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 認証ダイアログの表示
if not st.session_state.authenticated:
    st.text("このページは認証が必要です")
    password = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        if password == os.getenv("PAS"):
            st.session_state.authenticated = True
            st.success("認証に成功しました！")
            st.rerun()  # 認証成功後にリロード
        else:
            st.error("ユーザー名またはパスワードが違います")
else:
    # タイトルの設定
    st.title("あいのりタクシーアプリ🚕👫　　タクともver3.6")

    # 出発地点の入力フォーム (デフォルトで渋谷のNHKの住所を設定)
    start_address = st.text_input("出発地点を入力してください", placeholder="東京都渋谷区神南2-2-1 NHK放送センター")

    # # .envファイルを読み込む
    # load_dotenv()

    # Google Maps APIキーの読み込み
    api_key = os.environ["MAP_KEY"]

    # ファイルアップロード
    uploaded_file = st.file_uploader("Excelファイルをアップロードしてください", type=["xlsx"])

    # APIアクセス制限
    api_access_count = 0
    max_api_access = 500

    # Google Maps Geocoding APIを使用して住所から座標を取得する関数
    def geocode_address(address, api_key):
        global api_access_count
        if api_access_count >= max_api_access:
            st.error("APIアクセスが1000回を超えました。処理を中断します。")
            st.stop()  # ストリームリットの処理を停止
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={api_key}"
        response = requests.get(url)
        api_access_count += 1
        
        if response.status_code == 200:
            data = response.json()
            if data['results']:
                location = data['results'][0]['geometry']['location']
                return (location['lat'], location['lng'])  # 緯度・経度を返す
            else:
                return None
        else:
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
        dist_matrix = np.array([
            [
                geodesic(Point(c1), Point(c2)).km if c1 and c2 else float('inf')
                for c2 in coords
            ] for c1 in coords
        ])
        
        dbscan = DBSCAN(eps=2, min_samples=2, metric="precomputed")
        clusters = dbscan.fit_predict(dist_matrix)
        return clusters

    def decode_polyline(encoded_polyline):
        """エンコードされたポリラインをデコードしてリスト形式に変換する"""
        return convert.decode_polyline(encoded_polyline)

    def are_routes_similar(start, dest1, dest2, api_key):
        global api_access_count
        if api_access_count >= max_api_access:
            st.error("APIアクセスが1000回を超えました。処理を中断します。")
            st.stop()  # ストリームリットの処理を停止

        url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline"
        }

        # dest1の座標を取得
        dest1_location = geocode_address(dest1, api_key)
        if not dest1_location:
            print(f"目的地1の座標が取得できませんでした: {dest1}")
            return False

        # dest2の座標を取得
        dest2_location = geocode_address(dest2, api_key)
        if not dest2_location:
            print(f"目的地2の座標が取得できませんでした: {dest2}")
            return False

        # APIアクセス数のカウントをインクリメント
        api_access_count += 2

        # ペイロード1（dest1へのルート）
        payload1 = {
            "origin": {
                "location": {
                    "lat_lng": {
                        "latitude": start[0],  # 緯度
                        "longitude": start[1]  # 経度
                    }
                }
            },
            "destination": {
                "location": {
                    "lat_lng": {
                        "latitude": dest1_location[0],  # 緯度
                        "longitude": dest1_location[1]  # 経度
                    }
                }
            },
            "travel_mode": "DRIVE",
            "routing_preference": "TRAFFIC_AWARE"
        }

        # ペイロード2（dest2へのルート）
        payload2 = {
            "origin": {
                "location": {
                    "lat_lng": {
                        "latitude": start[0],  # 緯度
                        "longitude": start[1]  # 経度
                    }
                }
            },
            "destination": {
                "location": {
                    "lat_lng": {
                        "latitude": dest2_location[0],  # 緯度
                        "longitude": dest2_location[1]  # 経度
                    }
                }
            },
            "travel_mode": "DRIVE",
            "routing_preference": "TRAFFIC_AWARE"
        }

        # APIリクエストを送信して、レスポンスを取得
        response1 = requests.post(url, json=payload1, headers=headers)
        response2 = requests.post(url, json=payload2, headers=headers)

        # レスポンスのステータスコードを確認
        if response1.status_code == 200 and response2.status_code == 200:
            data1 = response1.json()
            data2 = response2.json()

            if 'routes' not in data1 or 'routes' not in data2 or not data1['routes'] or not data2['routes']:
                print(f"ルートが見つかりませんでした: {dest1} または {dest2}")
                return False

            # 各ルートのポリラインをデコードしてステップに分解
            route1_polyline = data1['routes'][0]['polyline']['encodedPolyline']
            route2_polyline = data2['routes'][0]['polyline']['encodedPolyline']

            # ポリラインをデコードして座標リストに変換
            route1_steps = decode_polyline(route1_polyline)
            route2_steps = decode_polyline(route2_polyline)

            # ステップを比較してルートが似ているかをチェック
            similar_step_count = 0
            for step1, step2 in zip(route1_steps, route2_steps):
                # ステップの終点（座標）が近いかどうかを判定
                if geodesic(
                    (step1['lat'], step1['lng']),
                    (step2['lat'], step2['lng'])
                ).km < 0.1:  # 100m以内なら同じステップとみなす
                    similar_step_count += 1

            # 少なくとも50％のステップが類似していればルートは同じとみなす
            min_similar_steps = int(0.5 * min(len(route1_steps), len(route2_steps)))
            similar = similar_step_count >= min_similar_steps
            print(f"ルートが類似しているか: {similar}")
            return similar
        else:
            print(f"ルートが見つかりませんでした。レスポンスコード: {response1.status_code} {response2.status_code}")
            return False

    # 住所の座標が不明な場合はデフォルト住所の座標を使用する関数
    def get_start_coords(start_address, api_key):
        return geocode_address(start_address, api_key)

    # メイン処理の結果をキャッシュして保存
    @st.cache_data
    def process_excel_data(start_coords, df):
        global api_access_count

        people = []
        coords = []  # 座標リスト
        invalid_addresses = []  # 無効な住所リスト

        for index, row in df.iterrows():
            person = {
                "name": row["Name"],  # "Name"列から取得
                "address": row["Address"]  # "Address"列から取得
            }
            people.append(person)

            # 住所の座標を取得
            location = geocode_address(person["address"], api_key)
            if location:
                coords.append(location)  # 緯度・経度をcoordsリストに追加
            else:
                coords.append(None)  # 座標が取得できなかった場合はNone
                invalid_addresses.append(person)  # 無効な住所リストに追加

        if len(people) < 1:
            print("十分な住所データが取得できませんでした。")
            return None, None, None, None
        else:
            # 無効な住所を除いてクラスタリング実行
            valid_people = [person for person, coord in zip(people, coords) if coord is not None]
            valid_coords = [coord for coord in coords if coord is not None]
            
            if len(valid_people) > 1:
                clusters = create_clusters(valid_people, valid_coords)
            else:
                clusters = [-1] * len(valid_people)  # クラスタリングできない場合は全て未分類とする
            
            # クラスタごとに人をまとめる
            taxi_groups = {}
            excluded_people = []
            for i, cluster_id in enumerate(clusters):
                if cluster_id != -1:
                    if cluster_id not in taxi_groups:
                        taxi_groups[cluster_id] = []
                    if len(taxi_groups[cluster_id]) < 3:  # タクシーに3人まで乗れるようにする
                        taxi_groups[cluster_id].append(valid_people[i])
                    else:
                        excluded_people.append(valid_people[i])  # 3人以上のグループは除外
                else:
                    excluded_people.append(valid_people[i])  # クラスタIDが-1（未分類）の場合は除外

            # 除外された人を既存のタクシーグループに追加
            for person in excluded_people:
                added_to_group = False
                for cluster_id, group in taxi_groups.items():
                    if len(group) < 3:
                        if are_routes_similar(start_coords, group[0]['address'], person['address'], api_key):
                            taxi_groups[cluster_id].append(person)
                            added_to_group = True
                            break
                if not added_to_group:
                    print(f"除外された人: {person['name']} - {person['address']}")

            # 新しく除外された人同士をグループ化するロジック
            new_group_id = max(taxi_groups.keys(), default=0) + 1

            # 各人がどのタクシーグループに属しているかを追跡する辞書
            person_to_group = {person['name']: None for person in excluded_people}

            for i in range(len(excluded_people)):
                for j in range(i + 1, len(excluded_people)):
                    if are_routes_similar(start_coords, excluded_people[i]['address'], excluded_people[j]['address'], api_key):
                        # どちらの人もまだどのグループにも属していない場合
                        if person_to_group[excluded_people[i]['name']] is None and person_to_group[excluded_people[j]['name']] is None:
                            # 新しいグループを作成して両方追加
                            if new_group_id not in taxi_groups:
                                taxi_groups[new_group_id] = []
                            if len(taxi_groups[new_group_id]) < 3:  # グループに3人以上追加しないように制限
                                taxi_groups[new_group_id].append(excluded_people[i])
                                taxi_groups[new_group_id].append(excluded_people[j])
                                person_to_group[excluded_people[i]['name']] = new_group_id
                                person_to_group[excluded_people[j]['name']] = new_group_id
                        elif person_to_group[excluded_people[i]['name']] is None:
                            # excluded_people[i]だけがグループに所属していない場合
                            group_id = person_to_group[excluded_people[j]['name']]
                            if len(taxi_groups[group_id]) < 3:
                                taxi_groups[group_id].append(excluded_people[i])
                                person_to_group[excluded_people[i]['name']] = group_id
                        elif person_to_group[excluded_people[j]['name']] is None:
                            # excluded_people[j]だけがグループに所属していない場合
                            group_id = person_to_group[excluded_people[i]['name']]
                            if len(taxi_groups[group_id]) < 3:
                                taxi_groups[group_id].append(excluded_people[j])
                                person_to_group[excluded_people[j]['name']] = group_id
                        # すでに両方の人が異なるグループに属している場合、何もしない
                new_group_id += 1

            # 最終的な結果を返す
            return taxi_groups, valid_people, invalid_addresses, start_coords

    # キャッシュされたデータを読み込む
    if uploaded_file and start_address and api_key:
        start_coords = get_start_coords(start_address, api_key)
        df = pd.read_excel(uploaded_file)
        
        # メイン処理をキャッシュして実行
        taxi_groups, valid_people, invalid_addresses, start_coords = process_excel_data(start_coords, df)

        if taxi_groups is not None:
            # グループを3人ずつに分割して表示
            result_data = []
            for cluster_id, group in taxi_groups.items():
                for i in range(0, len(group), 3):
                    sub_group = group[i:i+3]
                    taxi_group = f"Taxi {cluster_id + 1}"
                    for person in sub_group:
                        distance = geodesic(start_coords, geocode_address(person["address"], api_key)).km
                        taxi_fee, taxi_fee_midnight = calculate_taxi_fare(distance)
                        result_data.append({
                            "Taxi": taxi_group,
                            "Name": person['name'],
                            "Address": person['address'],
                            "Taxi Fee (Normal)": f"{taxi_fee}円",
                            "Taxi Fee (Midnight)": f"{taxi_fee_midnight}円" if taxi_fee_midnight else "N/A"
                        })

            # 無効な住所を結果の最後に追加
            for person in invalid_addresses:
                result_data.append({
                    "Taxi": "N/A",
                    "Name": person['name'],
                    "Address": person['address'],
                    "Taxi Fee (Normal)": "N/A",
                    "Taxi Fee (Midnight)": "N/A"
                })

            # エクセルファイルに出力
            if st.button("結果をファイル作成する"):
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
    else:
        st.info("出発地点とファイルをアップロードしてください。")
