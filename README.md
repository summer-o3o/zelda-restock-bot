# 🎮 닌텐도 스토어 재입고 알림 봇

닌텐도 스토어 상품 페이지를 **1분마다** 확인해서, 품절이던 상품이 다시 구매 가능해지면 디스코드로 알려주는 봇이에요.
GitHub Actions에서 돌아가서 서버 없이 무료로 24시간 동작해요.

지금 확인하는 상품: [Nintendo Switch 2 Pro 컨트롤러 젤다의 전설 40주년 애니버서리 에디션](https://store.nintendo.co.kr/beeafstdakor)

## 동작 방식

```
cron-job.org (5분마다 실행 신호)
   └─▶ GitHub Actions 실행 (restock.yml)
         ├─ data 브랜치에서 이전 상태(state.json) 불러오기
         ├─ 1분 간격으로 5번 상품 페이지 확인
         │    └─ 품절 → 구매 가능으로 바뀌면 디스코드 알림
         └─ 상태를 data 브랜치에 저장
```

- 재입고 알림은 **바뀌는 순간 한 번만** 보내요. 다시 품절됐다가 또 재입고되면 그때 다시 알려줘요.
- 처음 실행할 때 품절이면 기록만 하고, 이미 구매 가능하면 바로 알려줘요.
- 알림만 보내고 **자동 구매는 하지 않아요.**

### 재고 판단 방법

상품 페이지 가격 옆의 재고 표시를 읽어요.

| 페이지 표시 | 판단 |
|---|---|
| `<div class="stock unavailable">품절</div>` | 품절 |
| `<div class="stock available">…</div>` | 구매 가능 |
| 표시를 못 찾으면 상품 데이터의 `is_salable` 값 | 보조 판단 |

## 설치 방법

### 1. 디스코드 봇 만들기

1. [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**
2. **Bot** 메뉴: 이름·아이콘 설정, **Public Bot** 켜기, **Reset Token**으로 토큰 발급
   - Privileged Gateway Intents는 세 개 모두 꺼두기
3. **General Information**에서 **Application ID** 복사

### 2. 알림 받을 서버에 봇 초대

아래 주소의 `APPLICATION_ID`를 바꿔서 서버 관리자에게 전달해요.

```
https://discord.com/oauth2/authorize?client_id=APPLICATION_ID&scope=bot&permissions=19456
```

권한은 **채널 보기, 메시지 보내기, 링크 임베드** 세 개만 있어요.
`@everyone` 멘션까지 쓰려면 `permissions=150528`(Mention Everyone 추가)로 초대해요.

### 3. GitHub Secrets 등록

저장소 **Settings → Secrets and variables → Actions**

| 이름 | 값 | 필수 |
|---|---|---|
| `DISCORD_BOT_TOKEN` | 봇 토큰 | ✅ |
| `DISCORD_CHANNEL_IDS` | 알림 올릴 채널 ID (여러 개면 `111,222`) | 채널 알림 쓸 때 |
| `DISCORD_USER_IDS` | DM 받을 사용자 ID (여러 개면 `111,222`) | DM 쓸 때 |
| `RESTOCK_MENTION` | 알림에 붙일 멘션. 예: `@everyone`, `<@&역할ID>` | 선택 |
| `DISCORD_WEBHOOK_URL` | 웹후크로도 보낼 때 | 선택 |

- 채널 ID·사용자 ID는 디스코드 **설정 → 고급 → 개발자 모드**를 켠 뒤 우클릭 → **ID 복사**
- DM은 봇과 **같은 서버에 있는 사람**에게만 보낼 수 있어요.

### 4. 봇 첫 로그인 (한 번만)

디스코드는 한 번도 접속한 적 없는 봇의 메시지 전송을 막아요.
**Actions → 봇 첫 로그인 (한 번만) → Run workflow**

연결 확인은 **Actions → 봇 테스트 메시지 → Run workflow**

### 5. 5분마다 실행 (cron-job.org)

1. GitHub **Fine-grained token**: 이 저장소 포함, 권한 **Actions: Read and write**
2. cron-job.org에서 작업 생성
   - URL: `https://api.github.com/repos/<계정>/zelda-restock-bot/actions/workflows/restock.yml/dispatches`
   - 주기: Every 5 minutes
   - Method: `POST`
   - Headers
      - `Accept: application/vnd.github+json`
      - `Authorization: Bearer <토큰>`
      - `X-GitHub-Api-Version: 2022-11-28`
   - Body: `{"ref":"main"}`
3. **TEST RUN** 결과가 `204`면 성공

## 다른 상품으로 바꾸기

`restock_bot.py` 위쪽의 `PRODUCT_URL`, `PRODUCT_NAME`만 바꾸면 돼요. 닌텐도 스토어 상품 페이지라면 같은 방식으로 동작해요.

## 기록 확인

- 상태: `data` 브랜치의 `state.json`
- 기록: `data` 브랜치의 `log.md` (재입고·품절·확인 실패가 있을 때만 기록)
- 매 확인 결과는 **Actions 실행 로그**에서 볼 수 있어요.

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 로그에 `⚠️ 재고를 확인하지 못함 (error)` | 스토어 접속 실패. 계속되면 접속 차단(403) 가능성 |
| 로그에 `⚠️ 재고를 확인하지 못함 (unknown)` | 상품 페이지 구조가 바뀐 것. 판단 코드 수정 필요 |
| `전송 실패 403` | 봇에게 채널 권한이 있는지, DM 대상이 봇과 같은 서버에 있는지 |
| `전송 실패 401` | `DISCORD_BOT_TOKEN`이 맞는지 |

## 비용

GitHub Actions(Public 저장소), cron-job.org, Discord 모두 무료예요.
