import time
from playwright.sync_api import sync_playwright
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
# 🕸️ 2. スクレイピング処理本体
# ==========================================
def run_scraper():
    url = "http://h-suimon.la.coocan.jp/"
    print(f"\n【{time.strftime('%X')}】最新の水門データを解析中...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            page.wait_for_timeout(5000)
            
            frame = page.frames[1]
            text = frame.locator("body").inner_text()
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            observation_time = "-"
            upstream_level = 0.0
            downstream_level = 0.0
            total_discharge = 0.0
            open_gates_count = "-" # 仮設定
            
            # 🌟 観測日時を抽出
            for line in lines[:20]:
                match = re.search(r"\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}", line)
                if match:
                    observation_time = match.group()
                    break
                    
            # 🌟 水位差イメージ図から水位を抽出
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

            # 🌟 【修正】リアルタイム全放流量を抽出
            # ページ内で最初に出てくる「m³/s」の1つ上の行を取得します
            for i, line in enumerate(lines):
                if line == "m³/s":
                    try:
                        total_discharge = float(lines[i-1])
                        break # 最初の1個を見つけたら探索終了
                    except ValueError:
                        pass
                        
            # 🌟 【テスト用】強制的に開放状態にする！
            is_open = True
                    
            browser.close()

        # ==========================================
        # 🔔 通知判定とFirestore更新
        # ==========================================
        doc_ref = db.collection('gates').document('hachiroko')
        
        # 1. 変更前のデータを取得して、以前の状態をチェック
        doc_snap = doc_ref.get()
        previous_is_open = False
        if doc_snap.exists:
            previous_is_open = doc_snap.to_dict().get('is_open', False)

        # 2. 新しいデータをFirebaseに保存
        print("Firestoreのデータを更新しています...")
        doc_ref.set({
            'observation_time': observation_time,
            'upstream_level': upstream_level,
            'downstream_level': downstream_level,
            'total_discharge': total_discharge,
            'open_gates_count': open_gates_count,
            'is_open': is_open
        }, merge=True)
        print(f"✨ 送信完了 ➔ 放流量:{total_discharge}m³/s / 水門:{'開放' if is_open else '閉鎖'}")

        # 3. もし「閉鎖 ➔ 開放」に変わっていたら通知を一斉送信！
        if True:
            print("🚨 水門の開放を検知！名簿の全員にプッシュ通知を送信します！")
            
            # Firestoreの「fcm_tokens」名簿から全員の宛先を取得
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
        print(f"❌ エラーが発生しました（次回ループで再トライ）: {e}")

# ==========================================
# 🔁 3. 10分おきの無限ループ実行（最長約6時間）
# ==========================================
run_scraper()
    
