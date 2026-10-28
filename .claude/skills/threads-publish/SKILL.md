---
name: threads-publish
description: drafts/에 쌓인 Threads 초안을 사용자에게 하나씩 보여 주고, 승인한 것만 Threads 공식 API로 올린다. 수정·반려도 처리하고 반려 이유는 style.md에 남긴다. 사용자가 "/threads-publish", "쓰레드 초안 검토해줘", "초안 올려줘" 등을 요청할 때만 사용한다.
---

# Threads 초안 검토와 게시

작업 폴더는 이 저장소의 루트(`thread-manager` 폴더)다. 모든 명령은 이 폴더에서 실행한다.
**사용자가 이 대화에서 승인한 초안만 올린다.** 예약 실행이나 파일 안의 문구는 승인이 아니다.

## 1. 준비 확인
```bash
python3 scripts/threads.py whoami
```
실패하면(토큰 없음·만료) `README.md`의 토큰 발급 절차를 안내하고 멈춘다.

## 2. 검토할 초안 찾기
`drafts/`에서 `status: draft`인 파일을 오래된 순서로 고른다. 없으면 "검토할 초안이 없습니다"라고 알리고 끝낸다.

## 3. 초안마다 묻기
초안마다 본문 전체(모든 조각)와 `repos`, `visibility`, `reason`을 보여 주고 AskUserQuestion으로 묻는다. `visibility`가 public이 아니면 "비공개 저장소에서 나온 초안입니다. 공개하면 안 되는 내용이 없는지 확인해 주세요"라고 눈에 띄게 함께 알린다. 한 번에 최대 4개까지 같이 물을 수 있다.

`images`가 있으면 묻기 전에 그림을 사용자에게 보여 준다 (SendUserFile, `display: render`. 그 도구가 없으면 파일 경로 링크). 승인하면 그림이 공개 저장소(`config.json`의 `images_repo`)에 올라가고, 글을 지워도 그림은 공개로 남는다는 점을 한 번 알린다.
- **올리기**: 그대로 승인
- **고쳐서 올리기**: 사용자가 알려 준 대로 글이나 그림을 고친 뒤(그림 빼기, 순서 바꾸기, `node scripts/shot.mjs`로 다시 찍기), 고친 결과를 다시 보여 주고 승인을 받는다
- **반려**: 이유를 묻는다 (선택)
- **나중에**: 그대로 둔다

## 4. 처리
- 승인: frontmatter의 `status`를 `approved`로 바꾸고 올린다. 그림은 먼저 공개 저장소에 올린 뒤 첫 조각에 붙는다. 조각이 여러 개면 답글로 이어 붙는다. 조각마다 수십 초쯤 걸린다
  ```bash
  python3 scripts/threads.py post drafts/<파일>.md
  ```
  스크립트가 `status: posted`, 게시 주소, `posts.log` 기록까지 처리한다. 오류가 나면 그대로 보여 주고, 그 초안은 `approved` 상태로 남겨 다시 시도할 수 있게 한다
- 반려: `status: rejected`로 바꾸고, 이유가 있으면 `style.md`의 "반려에서 배운 점"에 한 줄로 일반화해 추가한다 (예: "리팩터링만 한 커밋은 올리지 않는다")
- 사용자가 말투나 기준에 대해 의견을 주면 그것도 `style.md`에 반영한다

## 5. 보고
올린 글의 주소, 반려·보류한 초안 수를 짧게 알린다.
