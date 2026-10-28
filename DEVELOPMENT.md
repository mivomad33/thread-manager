# 개발 문서

**한국어** | [English](DEVELOPMENT.en.md) · [README로 돌아가기](README.md)

상위 폴더(`config.json`의 `projects_root`, 기본 `..`)에 있는 프로젝트들의 작업 내역을 보고 Threads 글 초안을 만들고, 승인한 것만 올립니다.

```
예약 실행 → /threads-draft  : 새 커밋 수집 → 올릴지 판단 → drafts/에 초안 저장 (게시 안 함)
사용자     → /threads-publish : 초안 검토 → 승인 / 수정 / 반려 → 승인한 것만 게시
```

## 파일
| 파일 | 내용 |
|---|---|
| `config.json` | 제외할 폴더, 한 번에 만들 초안 수 |
| `style.md` | 올릴 것과 올리지 않을 것, 말투. 반려 이유가 여기 쌓입니다 |
| `state.json` | 저장소별 마지막 확인 지점 (자동 생성) |
| `drafts/` | 초안. `status`: draft → approved → posted, 또는 rejected |
| `drafts/images/` | 초안에 붙일 그림 (스크린샷, 저장소의 그림) |
| `backlog.json` | 상한(하루 3개)에 밀린 후보 주제. 다음 실행에서 다시 고르고, 14일이 지나면 버립니다 |
| `posts.log` | 올린 글 기록 (JSON Lines) |
| `.env` | Threads 토큰 (git에 넣지 않음) |
| `scripts/collect.py` | 커밋 수집, `--save`로 확인 지점 저장 |
| `scripts/threads.py` | 토큰 관리, 초안 검사, 이미지 업로드, 게시 |
| `scripts/shot.mjs` | 웹 페이지 스크린샷 (Playwright). 처음에 `npm install` 필요 |

`state.json`, `backlog.json`, `posts.log`, `drafts/` 안의 초안과 그림은 실행할 때 생기는 데이터라 git에 넣지 않습니다.
비공개 저장소 이름과 커밋, 아직 공개하지 않은 초안이 들어 있기 때문입니다.

## 그림
초안을 쓸 때 화면이 있는 주제면 배포된 공개 사이트(또는 데모)를 찍거나, 저장소에 이미 있는 그림을 씁니다.
개발 서버는 공개 저장소이고 로그인 없이 데모 데이터로 뜰 때만 씁니다. 찍은 그림은 Claude가 열어 보고
개인 정보가 보이면 버립니다.

Threads API는 공개 주소의 이미지만 받기 때문에, 게시를 승인하면 그림을 공개 저장소
[mivomad33/threads-images](https://github.com/mivomad33/threads-images)에 올리고 그 주소로 게시합니다.
반려한 초안의 그림은 올라가지 않습니다. 한 번 올린 그림은 글을 지워도 저장소에 공개로 남습니다.

다른 계정으로 쓸 때는 이미지용 공개 저장소를 따로 만들고 `config.json`의 `images_repo`를 바꿉니다.

## 대상 저장소
실행할 때마다 `projects_root` 바로 아래의 git 저장소를 모두 찾습니다. 새 프로젝트는 자동으로 포함되고,
처음 발견되면 최근 7일 커밋부터 봅니다. 빼고 싶은 폴더는 `config.json`의 `exclude`에 넣습니다.

저장소마다 공개 여부(`gh`로 확인)를 함께 봅니다. 공개가 아닌 저장소에서 나온 초안은 저장소 링크와
공개 전 세부 내용을 피해서 쓰고, 검토할 때 비공개 출처라고 따로 알립니다.

## Threads 토큰 발급 (처음 한 번)
1. [Meta for Developers](https://developers.facebook.com/apps)에 Facebook 계정으로 로그인하고 개발자로 등록합니다 (휴대폰 인증)
2. 앱 만들기 → 사용 사례로 **Threads API 액세스**를 선택합니다 (비즈니스 포트폴리오는 연결하지 않아도 됩니다)
3. 사용 사례 맞춤 설정 → 권한에 `threads_content_publish`를 추가합니다 (`threads_basic`은 기본 포함)
4. 앱 역할 → 사람 추가 → **Threads 테스터**로 내 Threads 계정을 추가하고, Threads 앱의 설정 → 계정 → 웹사이트 권한 → 초대에서 수락합니다
5. 사용 사례 설정의 **사용자 토큰 생성기**에서 **액세스 토큰 생성하기**를 누르고 Threads 팝업에서 승인합니다. 60일짜리 장기 토큰이 나옵니다 (공개 계정만 가능)
6. `.env`에 저장합니다
   ```
   THREADS_ACCESS_TOKEN=...
   ```
7. 확인합니다: `python3 scripts/threads.py whoami`

장기 토큰은 60일 뒤 만료됩니다. 게시할 때 발급 후 30일이 지났으면 자동으로 갱신합니다.
60일 넘게 게시하지 않았다면 5~6단계를 다시 합니다.
단기 토큰(1시간)을 받았다면 `.env`에 `THREADS_APP_SECRET`을 넣고 `python3 scripts/threads.py exchange <단기토큰>`으로 바꿉니다.

## 예약 실행
Claude 데스크톱 앱의 예약 작업(Scheduled)으로 `threads-draft`를 주기적으로 돌립니다. 예: 평일 오전 10시(`0 10 * * 1-5`).
예약 작업의 지시문에는 아래 내용을 넣습니다.

- `.claude/skills/threads-draft/SKILL.md`를 읽고 그대로 따릅니다. 명령은 이 저장소 폴더에서 실행합니다
- 절대 게시하지 않습니다 (`threads.py post`를 실행하지 않고, `status`를 `approved`로 바꾸지 않습니다)
- 대상 저장소의 파일은 읽기만 합니다
- 끝나면 살펴본 커밋 수, 새 초안, 올리지 않기로 한 주제를 짧게 보고합니다

예약 작업은 앱이 켜져 있을 때 실행됩니다. 앱이 꺼져 있었다면 다음에 켤 때 실행됩니다.

## 자주 쓰는 명령
```bash
python3 scripts/collect.py
python3 scripts/collect.py --save
python3 scripts/threads.py check drafts/<파일>.md
python3 scripts/threads.py quota
node scripts/shot.mjs <url> drafts/images/<이름>.png --mobile
```
