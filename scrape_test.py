import time
import urllib.request  # 🌟 Python標準の通信ツール（追加インストール不要で爆速）
import re
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
# 🕸️ 2. データ解析処理本体（GAS経由）
# ==========================================
def run_scraper():
    # 👇 【超重要】ここに、さっきGASでコピーした「ウェブアプリ URL」を貼り付けてください！
    GAS_URL = "https://script.google.com/macros/s/AKfycbxVNeXzzFGuLHF5mDTzKtmZgzWBJTs0s7ZAzJh-mtBmbSlqUtbsvECLrmFqArnNwg0hlg/exec"
    
    print(f"\n【{time.strftime('%X')}】GAS経由で最新の水門データを解析中...")

    try:
        # 🌟 Playwrightの代わりに、GASのURLを開いて文字を吸い出す（1秒で終わります）
        req = urllib.request.Request(GAS_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            text = response.read().decode('utf-8')
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        observation_time = "-"
        upstream_level = 0.0
        downstream_level = 0.0
        total_discharge = 0.0
        open_gates_count = "-" # 仮設定
        
        # 🌟 1. 観測日時を抽出（GASでデータが合体しているので探索範囲を少し広げます）
        for line in lines[:40]:
            match = re.search(r"\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}", line)
            if match:
                observation_time = match.group()
                break
                
        # 🌟 2. 水位差イメージ図から水位を抽出
        for i, line in enumerate(lines):
            if line == "水位差イメージ図":
                floats_found = []
                for j in range(1, 15):
                    if i + j < len(lines):
                        match = re.search(r"^\d+\.\d+$", lines[i+j])
                        if match:
                            floats_found.append(float(match.group()))
                
                if len(floats_found) >= 2:
                    upstream_level = floats_found[0]
                    downstream_level = floats_found[1]
                break

        # 🌟 3. リアルタイム全放流量を抽出
        for i, line in enumerate(lines):
            if line == "m³/s":
                try:
                    total_discharge = float(lines[i-1])
                    break # 最初の1個を見つけたら探索終了
                except ValueError:
                    pass
                    
        # 🌟 4. 放流量が0より大きければ開放判定！
        is_open = total_discharge > 0.0

        # ==========================================
        # 🔔 通知判定とFirestore更新
        # ==========================================
        doc_ref = db.collection('gates').document('hachiroko')
        
        # 変更前のデータを取得して、以前の状態をチェック
        doc_snap = doc_ref.get()
        previous_is_open = False
        if doc_snap.exists:
            previous_is_open = doc_snap.to_dict().get('is_open', False)

        # 新しいデータをFirebaseに保存
        print("Firestoreのデータを更新しています...")
        doc_ref.set({
            'observation_time': observation_time,
            'upstream_level': upstream_level,
            'downstream_level': downstream_level,
            'total_discharge': total_discharge,
            'open_gates_count': open_gates_count,
            'is_open': is_open
        }, merge=True)
        print(f"✨ 送信完了 ➔ 日時:{observation_time} / 上流:{upstream_level} / 下流:{downstream_level} / 放流:{total_discharge}m³/s")

        # もし「閉鎖 ➔ 開放」に変わっていたら通知を一斉送信！
        if is_open and not previous_is_open:
            print("🚨 水門の開放を検知！名簿の全員にプッシュ通知を送信します！")
            
            tokens_snapshot = db.collection('fcm_tokens').get()
            tokens = [doc.id for doc in tokens_snapshot]
            
            if tokens:
                message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title='水門アラート🚨',
                        body=f'八郎湖防潮門が開放されました。（観測日時: {observation_time}）',
                    ),
                    tokens=tokens,
                )
                response = messaging.send_each_for_multicast(message)
                print(f'通知送信完了: {response.success_count}件成功 / {response.failure_count}件失敗')
            else:
                print("※通知を送る宛先（名簿）が空でした。")

    except Exception as e:
        import traceback
        print("❌ エラーの詳細な原因:")
        traceback.print_exc()

# ==========================================
# 🚀 3. スクリプト実行
# ==========================================
if __name__ == "__main__":
    run_scraper()
    print("✅ 1回分の処理が完了し、プログラムを終了します。")
