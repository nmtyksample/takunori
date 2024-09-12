import requests
import urllib.parse
from geopy.distance import geodesic  # 距離計算用のライブラリ
from datetime import datetime

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
            return coordinates  # GSIは経度、緯度の順で返す
        else:
            print("住所が見つかりませんでした。")
            return None, None
    else:
        print("APIリクエストに失敗しました。")
        return None, None

# 距離を元にタクシー料金を計算する関数
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

# 出発地点と複数の目的地から最も遠い地点を見つけて料金を計算
def calculate_fare_from_start_to_farthest(start_address, destination_addresses):
    start_coords = geocode_with_retry(start_address)
    if not start_coords:
        return "出発地点の座標が取得できませんでした"

    max_distance = 0
    max_destination = None
    max_taxi_fee = 0
    max_taxi_fee_midnight = 0

    # 目的地ごとに距離と料金を計算
    for destination in destination_addresses:
        dest_coords = geocode_with_retry(destination)
        if not dest_coords:
            print(f"{destination} の座標が取得できませんでした")
            continue

        # 緯度経度で距離を計算
        distance_km = geodesic((start_coords[1], start_coords[0]), (dest_coords[1], dest_coords[0])).km

        # 距離に基づいてタクシー料金を計算
        taxi_fee, taxi_fee_midnight = calculate_taxi_fare(distance_km)

        # 最も遠い地点を探す
        if distance_km > max_distance:
            max_distance = distance_km
            max_destination = destination
            max_taxi_fee = taxi_fee
            max_taxi_fee_midnight = taxi_fee_midnight if taxi_fee_midnight else 0

    # 結果を返す
    return {
        "最も遠い目的地": max_destination,
        "通常料金": max_taxi_fee,
        "深夜料金": max_taxi_fee_midnight if max_taxi_fee_midnight else "適用なし"
    }

# ユーザーから出発地点を入力
start = input("出発地点の住所を入力してください: ")

# ユーザーから目的地を複数入力
destinations = []
while True:
    destination = input("目的地を入力してください (終了する場合はEnterを押してください): ")
    if destination == "":
        break
    destinations.append(destination)

# タクシー料金を計算
fare_result = calculate_fare_from_start_to_farthest(start, destinations)

# 結果を出力
print(f"最も遠い目的地: {fare_result['最も遠い目的地']}")
print(f"タクシー料金（通常料金）: {fare_result['通常料金']}円")
print(f"タクシー料金（深夜料金）: {fare_result['深夜料金']}")
