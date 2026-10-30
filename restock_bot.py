"""닌텐도 스토어 상품 재입고 알림 봇."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# ── 확인할 상품 ──
PRODUCT_URL = "https://store.nintendo.co.kr/beeafstdakor"
PRODUCT_NAME = "Nintendo Switch 2 Pro 컨트롤러 젤다의 전설 40주년 애니버서리 에디션"

# 한 번 실행할 때 1분 간격으로 5번 확인 (cron-job.org가 5분마다 실행)
CHECKS_PER_RUN = 5
CHECK_INTERVAL_SECONDS = 60

STATE_FILE = "state.json"
LOG_FILE = "log.md"
MAX_LOG_LINES = 1000
KST = timezone(timedelta(hours=9))

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
CHANNEL_IDS = [c.strip() for c in os.environ.get("DISCORD_CHANNEL_IDS", "").split(",") if c.strip()]
USER_IDS = [u.strip() for u in os.environ.get("DISCORD_USER_IDS", "").split(",") if u.strip()]
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
# 테스트용: 이 값이 있으면 이 주소를 한 번만 확인하고, 구매 가능이면 무조건 알림 (상태 저장 안 함)
TEST_PRODUCT_URL = os.environ.get("TEST_PRODUCT_URL", "").strip()
# 알림과 같이 보낼 멘션 (예: "@everyone" 또는 "<@&역할ID>"), 비워두면 멘션 없음
MENTION = os.environ.get("RESTOCK_MENTION", "").strip()

BOT_UA = "DiscordBot (https://github.com/summer-o3o/zelda-restock-bot, 1.0)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def now_kst():
    return datetime.now(KST)


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": BROWSER_UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def describe_page(html):
    """판단이 안 될 때 원인을 보려고 페이지 요약을 만든다."""
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    title = re.sub(r"\s+", " ", title.group(1)).strip()[:80] if title else "(제목 없음)"
    return f"길이 {len(html)}자, 제목: {title}"


def detect_stock(html):
    """
    닌텐도 스토어(Magento) 상품 페이지에서 재고 상태를 읽는다.
    반환: "in"(구매 가능) / "out"(품절) / "unknown"(판단 불가)
    """
    # 1순위: 가격 옆 재고 표시  <div class="stock unavailable" ...><span>품절</span>
    block = re.search(r'product-info-stock-sku.*?class="stock (available|unavailable)"', html, re.S)
    if block:
        return "in" if block.group(1) == "available" else "out"

    # 2순위: 상품 데이터의 판매 가능 여부  "is_salable":"" / "is_salable":"1"
    salable = re.search(r'"is_salable"\s*:\s*"?(\w*)"?', html)
    if salable:
        return "in" if salable.group(1) in ("1", "true") else "out"

    return "unknown"


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def write_log(lines):
    if not lines:
        return

    old = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding="utf-8") as f:
            old = f.read().splitlines()
        if old and old[0].startswith("# "):
            old = old[2:]

    header = ["# 재입고 봇 기록", ""]
    body = (lines + [""] + old)[:MAX_LOG_LINES]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(header + body).rstrip() + "\n")


def post(url, payload, headers):
    body = json.dumps(payload).encode("utf-8")

    for _ in range(3):
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json", **headers},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code == 429:
                try:
                    wait = float(json.loads(detail).get("retry_after", 2))
                except Exception:
                    wait = 2
                time.sleep(wait + 0.5)
                continue
            print(f"전송 실패 {exc.code}: {detail[:300]}")
            return None
        except Exception as exc:
            print(f"전송 오류: {exc}")
            return None
    return None


def bot_headers():
    return {"Authorization": f"Bot {BOT_TOKEN}", "User-Agent": BOT_UA}


def notify(title, description, color):
    embed = {
        "title": title,
        "url": PRODUCT_URL,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "닌텐도 스토어"},
    }
    payload = {"embeds": [embed]}
    if MENTION:
        payload["content"] = MENTION
        payload["allowed_mentions"] = {"parse": ["everyone", "roles", "users"]}

    sent = 0

    if WEBHOOK_URL and post(WEBHOOK_URL, payload, {"User-Agent": "restock-bot"}) is not None:
        sent += 1

    for channel_id in CHANNEL_IDS:
        if post(f"https://discord.com/api/v10/channels/{channel_id}/messages", payload, bot_headers()) is not None:
            sent += 1

    # 개인 DM (봇과 같은 서버에 있는 사람만 가능)
    dm_payload = {"embeds": [embed]}
    for user_id in USER_IDS:
        dm = post("https://discord.com/api/v10/users/@me/channels",
                  {"recipient_id": user_id}, bot_headers())
        if dm and dm.get("id") and post(
                f"https://discord.com/api/v10/channels/{dm['id']}/messages",
                dm_payload, bot_headers()) is not None:
            sent += 1

    return sent


def main():
    if not (WEBHOOK_URL or (BOT_TOKEN and (CHANNEL_IDS or USER_IDS))):
        sys.exit("DISCORD_BOT_TOKEN + DISCORD_CHANNEL_IDS(또는 DISCORD_USER_IDS)를 설정해 주세요.")

    if TEST_PRODUCT_URL:
        html = fetch(TEST_PRODUCT_URL)
        status = detect_stock(html)
        print(f"[테스트] {TEST_PRODUCT_URL} 재고 상태: {status} ({describe_page(html)})")
        if status == "in":
            sent = notify(
                "🧪 [테스트] 재입고 알림",
                f"테스트 상품이 구매 가능해서 보낸 알림이에요.\n{TEST_PRODUCT_URL}",
                0x2ECC71,
            )
            print(f"테스트 알림 전송: {sent}곳")
        else:
            print("테스트 상품이 구매 가능 상태가 아니라 알림을 보내지 않았어요.")
        return

    state = load_state()
    log = []

    for attempt in range(CHECKS_PER_RUN):
        stamp = now_kst().strftime("%Y-%m-%d %H:%M:%S")

        try:
            html = fetch(PRODUCT_URL)
            status = detect_stock(html)
            if status == "unknown":
                print(f"[{stamp}] 재고 표시를 못 찾음: {describe_page(html)}")
        except Exception as exc:
            status = "error"
            print(f"[{stamp}] 페이지를 가져오지 못했어요: {exc}")

        previous = state.get("status")
        print(f"[{stamp}] 재고 상태: {status} (이전: {previous})")

        if status in ("in", "out") and status != previous:
            if status == "in":
                sent = notify(
                    f"🎮 재입고! {PRODUCT_NAME}",
                    "지금 닌텐도 스토어에서 구매할 수 있어요!",
                    0x2ECC71,
                )
                log.append(f"- **{stamp}** ✅ 재입고 알림 전송 ({sent}곳)")
            elif previous == "in":
                log.append(f"- **{stamp}** ❌ 다시 품절")
            else:
                log.append(f"- **{stamp}** 🆕 첫 확인: 품절 상태")

            state = {"status": status, "changed_at": stamp}
            save_state(state)

        elif status in ("unknown", "error"):
            # 페이지 구조가 바뀌었거나 접속이 막힌 경우. 상태는 그대로 두고 기록만
            if state.get("last_problem") != status:
                log.append(f"- **{stamp}** ⚠️ 재고를 확인하지 못함 ({status})")
                state["last_problem"] = status
                save_state(state)
        elif state.get("last_problem"):
            state.pop("last_problem")
            save_state(state)

        if attempt < CHECKS_PER_RUN - 1:
            time.sleep(CHECK_INTERVAL_SECONDS)

    write_log(list(reversed(log)))


if __name__ == "__main__":
    main()
