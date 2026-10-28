---
name: threads-draft
description: 프로젝트 폴더(config.json의 projects_root)의 git 저장소에서 지난 확인 이후 커밋을 모아, 밀려 있던 후보 주제와 함께 Threads에 올릴 만한 것을 골라 초안을 drafts/에 쓴다. 게시는 하지 않는다. 예약 작업이 주기적으로 실행하거나, 사용자가 "/threads-draft", "쓰레드 초안 만들어줘" 등을 요청할 때 사용한다.
---

# Threads 초안 만들기

작업 폴더는 이 저장소의 루트(`thread-manager` 폴더)다. 모든 명령은 이 폴더에서 실행한다.
이 스킬은 **초안만 만든다. 절대 게시하지 않는다** (`threads.py post`를 실행하지 않는다).

## 1. 기준과 이력 읽기
- `style.md`: 올릴 것과 올리지 않을 것, 말투, 반려에서 배운 점
- `config.json`: 제외할 폴더(`exclude`), 한 번에 만들 초안 수 상한(`max_drafts_per_run`). 대상 저장소는 실행할 때마다 `projects_root` 아래에서 새로 찾는다
- `posts.log`(있으면): 이미 올린 글. 같은 이야기를 반복하지 않는다
- `backlog.json`(없으면 빈 목록): 지난 실행에서 상한에 밀려 초안으로 쓰지 못한 후보 주제 (형식은 4-2단계)
- `drafts/`의 기존 초안 중 `status: draft`, `approved`, `rejected`인 것. 아직 처리되지 않은 초안과 겹치지 않게 하고, 반려된 주제는 다시 꺼내지 않는다

## 2. 변경 내역 모으기
```bash
python3 scripts/collect.py
```
- 출력의 `repos`가 비어 있으면 새 커밋이 없는 것이다. 이때도 `backlog.json`에 후보가 있으면 3단계로 가서 후보만으로 고른다. 후보도 없으면 5단계(확인 지점 저장)로 건너뛴다
- `errors`가 있으면 마지막 보고에 적는다
- 저장소마다 `visibility`(public / private / internal / no-remote / unknown)와 `repo_url`(공개일 때만)이 붙어 있다
- 커밋 메시지만으로 내용이 불분명하면 해당 저장소에서 `git show <hash>`나 파일을 직접 읽어 확인한다. 저장소 파일은 읽기만 하고 고치지 않는다

## 3. 올릴지 판단하기
- 먼저 `backlog.json`에서 `first_seen`이 `backlog_max_age_days`일보다 오래된 후보를 지운다
- 새 커밋을 주제별로 묶는다 (예: 같은 기능을 위한 여러 커밋은 한 주제). 남은 후보와 같은 주제면 새로 만들지 않고 그 후보에 합친다 (커밋 추가, 요약 갱신, `first_seen`은 그대로)
- 새 주제와 후보를 함께 `style.md` 기준으로 판단한다. 애매하면 올리지 않는 쪽을 택한다. 올릴 만하지 않은 주제는 후보에도 넣지 않는다
- 초안은 `max_drafts_per_run`개까지. 가치가 큰 순서(출시 > 직접 써 볼 새 기능 > 해결한 문제·배운 점 > 진척)로 고르고, 가치가 비슷하면 오래된 후보를 먼저 고른다
- `visibility`가 public이 아닌 저장소는 더 조심한다. 이미 배포된 서비스로 확인되는 것(README의 서비스 주소 등)만 다루고, 저장소 링크·내부 구조·아직 공개하지 않은 기능 이름과 세부 내용은 쓰지 않는다. 애매하면 올리지 않는다
- 커밋만으로 공개 여부를 알 수 없는 기능은 README나 배포된 화면 관련 코드로 확인하고, 그래도 모르면 뺀다
- 올릴 것이 없으면 초안을 만들지 않는 것이 정상적인 결과다

## 4. 그림 준비
고른 주제마다 글을 보여 줄 그림이 있으면 1~3장을 준비한다. 없어도 되며, 억지로 넣지 않는다.
파일 이름은 `drafts/images/<초안 파일 이름>-01-<짧은 설명>.png` 처럼 짓는다.

구하는 순서:
1. **배포된 공개 사이트 스크린샷**: README, `repo_url`, 기존 초안에서 공개 주소를 찾는다. 바뀐 기능이 보이는 화면을 찍는다. 데모 페이지가 있으면 데모를 쓴다
   ```bash
   node scripts/shot.mjs <url> drafts/images/<이름>.png [--mobile] [--full] [--selector <css>] [--click <css>] [--wait <ms>]
   ```
   휴대폰 위주 서비스면 `--mobile`, 특정 부분만 보여 주려면 `--selector`를 쓴다
2. **저장소에 이미 있는 그림**: README 스크린샷, 문서 그림(회로도 등)을 `drafts/images/`로 복사한다. PNG/JPEG만 쓸 수 있다
3. **개발 서버 스크린샷**: 아래를 모두 만족할 때만 시도한다
   - 저장소가 public이다 (공개 전 화면이 비공개 저장소에서 새어 나가지 않게)
   - 실행 방법이 README나 문서에 있고, 로그인이나 실제 비밀값 없이 데모·시드 데이터로 화면이 나온다
   - 서버는 백그라운드로 띄우고, 찍은 뒤 반드시 끈다. 5분 안에 안 뜨면 포기한다
   - 저장소 파일은 고치지 않는다

찍거나 복사한 이미지는 **하나씩 직접 열어 본다**(Read). 아래에 해당하면 지우고 쓰지 않는다.
- 실제 개인 정보(이메일, 이름, 계좌·카드 번호, 실제 금융 데이터), 토큰, 내부 주소가 보인다
- 로그인 화면이나 오류 화면만 찍혔거나, 화면이 깨졌거나, 비어 있다
- 글 내용과 상관없는 화면이다

## 4-1. 초안 쓰기
파일: `drafts/YYYY-MM-DD-<저장소>-<짧은-영문-slug>.md`

```markdown
---
status: draft
repos: senseful
visibility: public
commits: f92a19f29d,ab12cd34ef
created: 2026-10-28T09:00:00+09:00
reason: 이 주제를 고른 이유 한 줄
images: 2026-10-28-senseful-review-01-result.png,2026-10-28-senseful-review-02-mobile.png
---
첫 번째 조각 (500자 이하)

---

두 번째 조각 (선택, 답글로 이어 붙음)
```

- `visibility`에는 수집 결과의 값을 적는다. 여러 저장소를 묶었으면 가장 덜 공개된 값을 적는다 (no-remote·unknown < private < internal < public)
- 링크는 `repo_url`이나 README에 적힌 공개 서비스 주소만 쓴다
- `images`는 `drafts/images/` 안의 파일 이름을 쉼표로 적는다. 그림이 없으면 이 줄을 빼고, 본문에서 그림을 언급하지 않는다. 그림은 첫 조각에 붙는다 (2장 이상이면 넘겨 보는 캐러셀)
- frontmatter 다음의 `---` 줄은 조각 구분자다. 본문 안에서 다른 용도로 `---`를 쓰지 않는다
- 비밀값, 토큰, 내부 경로(`/Users/...`), 개인 정보가 들어가지 않았는지 다시 확인한다
- 저장한 뒤 형식과 글자 수를 검사한다. 실패하면 고쳐서 다시 검사한다
  ```bash
  python3 scripts/threads.py check drafts/<파일>.md
  ```

## 4-2. 후보 목록 갱신
`backlog.json`을 다시 쓴다. 초안으로 쓴 후보는 빼고, 올릴 만하지만 상한에 밀린 주제는 넣는다.
```json
[
  {
    "topic": "노트 PDF 만들기 도구 묶음 (split-textbook, exam-sheets, note-pdf)",
    "summary": "어떤 이야기인지 두세 문장. 다음 실행에서 이것만 보고도 판단할 수 있게",
    "repos": "electricity-study",
    "visibility": "public",
    "commits": "70138e2991,3d7f54a995",
    "first_seen": "2026-10-28"
  }
]
```
후보가 없으면 `[]`로 둔다.

## 5. 확인 지점 저장
초안을 만들었든 아니든, 검토를 마쳤으면 저장한다. 다음 실행은 이 지점 이후의 커밋만 본다. 밀린 주제는 커밋이 아니라 `backlog.json`으로 이어진다.
```bash
python3 scripts/collect.py --save
```

## 6. 보고
짧게 보고한다.
- 살펴본 저장소와 커밋 수
- 만든 초안 목록: 파일 이름, 첫 줄, 고른 이유, 그림 수 (후보 목록에서 꺼낸 것이면 표시)
- 후보 목록: 남은 후보 수와 주제, 기한이 지나 버린 후보
- 올리지 않기로 한 주요 주제와 이유 (한 줄씩)
- 초안이 있으면: "`/threads-publish`로 검토하고 올릴 수 있습니다"
