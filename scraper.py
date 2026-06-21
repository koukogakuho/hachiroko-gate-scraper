import time
import urllib.request
import json
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from firebase_admin import messaging

# ==========================================
# ⚙️ 1. Firebaseへの接続準備
# ==========================================
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

# ==========================================
# 🕸️ 2. データ解析処理（JSONダイレクト・完全解読版）
# ==========================================
def run_scraper():
    # 👇 ここに新しく発行したGASのウェブアプリURLを貼り付けます
    GAS_URL = "https://script.google.com/macros/s/AKfycbxtmkaBay9DPqo1Y44b5ufgTkAt7eSN0iNpnYidgzOE9-CNN6zw_-V77gE-LLRF3KmySg/exec"
    
    print(f"\n【{time.strftime('%X')}】クラウドから生のJSONデータを取得中...")

    try:
        req = urllib.request.Request(GAS_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            raw_text = response.read().decode('utf-8', errors='ignore')
            
        if not raw_text.strip():
            print("🚨 エラー: GASから文字が届きませんでした。")
            return
            
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        if start_idx == -1 or end_idx == -1:
            print("🚨 エラー: データの中に { } が見つかりませんでした。")
            return
            
        json_text = raw_text[start_idx:end_idx+1]
        data = json.loads(json_text)
        
        # 🌟 データ抽出（完全解読に成功したID群）
        observation_time = data.get("time", "-")
        upstream_level = data.get("100010011", [0, 0])[1] / 100.0
        downstream_level = data.get("100010012", [0, 0])[1] / 100.0
        total_discharge = float(data.get("100010069", [0, 0])[1])
        open_gates_count = str(data.get("100010137", [0, 0])[1])
        is_open = total_discharge > 0.0

        # ==========================================
        # 🔔 Firestore更新と通知
        # ==========================================
        doc_ref = db.collection('gates').document('hachiroko')
        doc_snap = doc_ref.get()
        previous_is_open = False
        if doc_snap.exists:
            previous_is_open = doc_snap.to_dict().get('is_open', False)

        print("Firestoreのデータを更新しています...")
        doc_ref.set({
            'observation_time': observation_time,
            'upstream_level': upstream_level,
            'downstream_level': downstream_level,
            'total_discharge': total_discharge,
            'open_gates_count': open_gates_count,
            'is_open': is_open
        }, merge=True)
        print(f"✨ 送信完了 ➔ 日時:{observation_time} / 上流:{upstream_level}m / 下流:{downstream_level}m / 放流:{total_discharge}m³/s / 門数:{open_gates_count}")

        if is_open and not previous_is_open:
            print("🚨 水門の開放を検知！通知を送信します！")
            tokens_snapshot = db.collection('fcm_tokens').get()
            tokens = [doc.id for doc in tokens_snapshot]
            if tokens:
                message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title='水門アラート🚨',
                        body=f"""八郎湖防潮門が開放されました。（観測日時: {observation_time}）""",
                    ),
                    tokens=tokens,
                )
                response = messaging.send_each_for_multicast(message)
                print(f'通知送信完了: {response.success_count}件成功')

    except Exception as e:
        import traceback
        print("❌ エラーが発生しました:")
        traceback.print_exc()

if __name__ == "__main__":
    run_scraper()
    print("✅ 1回分の処理が完了しました。")
