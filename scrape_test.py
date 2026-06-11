import time # 🌟 時間を測るライブラリを追加
from playwright.sync_api import sync_playwright
import re
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

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
            open_gates_count = 0
            is_open = False
            
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
                    
            browser.close()

        # 📡 Firestoreに送信
        print("Firestoreのデータを更新しています...")
        doc_ref = db.collection('gates').document('hachiroko')
        doc_ref.set({
            'observation_time': observation_time,
            'upstream_level': upstream_level,
            'downstream_level': downstream_level,
            'total_discharge': total_discharge,
            'open_gates_count': open_gates_count,
            'is_open': is_open
        }, merge=True)

        print(f"✨ 送信完了 ➔ 上流:{upstream_level}m / 下流:{downstream_level}m")
    
    except Exception as e:
        print(f"❌ エラーが発生しました（次回ループで再トライ）: {e}")

# ==========================================
# 🔁 3. 10分おきの無限ループ実行（最長約6時間）
# ==========================================
# GitHub Actionsの制限時間（6時間＝360分）に安全に収まるよう、33回（5.5時間分）ループします
for loop_count in range(33):
    run_scraper()
    print("⏳ 次の更新まで10分間待機します...")
    time.sleep(600) # 600秒（10分）お休みする命令
