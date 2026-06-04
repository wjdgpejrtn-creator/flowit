development → release 동기화(staging 배포 트리거) PR을 **충돌 없이** 생성한다. 인자(선택): 동기화 요약 메모. 예: `/release-sync` 또는 `/release-sync connection 시리즈 + 재시드`

---

## 왜 이 커맨드가 필요한가 (반복 충돌의 정체)

release-sync PR을 **squash 머지**하면 release에 development 히스토리에 없는 `chore(release-sync)` 단일 커밋만 쌓인다. 그 결과 **`merge-base(release, development)`가 최초 baseline 커밋으로 고정**되고, 다음 sync는 baseline부터 통째로 merge 표면이 잡혀 **거대 충돌**이 난다(release-only 커밋은 전부 과거 sync 잔재 — 진짜 hotfix 아님). 이 커맨드는 **`-s ours`로 release를 development 트리로 덮어쓰면서 release를 parent로 편입**해 매번 충돌 0으로 만든다.

---

## Step 0. 사전 점검 (덮어쓰기 안전성 — 필수)

```bash
git fetch origin development release
# release에만 있는 커밋 = development로 덮어쓸 때 사라지는 것. 전부 sync 잔재여야 안전.
git log --oneline origin/development..origin/release
```

- 위 목록이 **전부 `chore(release-sync)` / `chore(release)` 잔재**면 `-s ours` 안전.
- **진짜 hotfix(release 직접 수정)가 1개라도 보이면 중단** → 그 커밋을 먼저 development로 cherry-pick한 뒤 진행(release-only 변경 유실 방지).
- 실제 배포 규모는 커밋 수가 아니라 **트리 diff**로 판단(merge-commit 과대보고):
  ```bash
  git diff --stat origin/release origin/development | tail -1
  ```

## Step 1. 충돌 없는 sync 브랜치 생성

날짜는 오늘(YYYY-MM-DD). 더티 트리면 `git stash push -- .claude/`로 비켜둔다.

```bash
DATE=<오늘>
git checkout -B chore/release-sync-$DATE origin/development
# release를 -s ours로 머지: 트리는 development 그대로, release는 parent로만 편입(충돌 0)
git merge -s ours --no-edit -m "chore(release-sync): development → release 동기화 ($DATE)" origin/release
# 검증: 트리가 development와 완전히 동일해야 함
[ "$(git rev-parse HEAD^{tree})" = "$(git rev-parse origin/development^{tree})" ] && echo "tree==development OK" || echo "FAIL"
```

`-s ours`는 현재(development) 트리를 유지하고 release 변경은 버린다 → Step 0에서 release-only가 sync 잔재뿐임을 확인했으므로 안전.

## Step 2. PR 본문 작성 (배포 effect + 재시드 반드시 포함)

본문은 파일로 작성(백틱·`$()` shell 평가 방지). 아래 4블록 필수:

1. **범위**: 트리 diff 규모(`git diff --stat origin/release origin/development`) + 주요 머지 PR 번호. 커밋 수 아닌 트리 기준.
2. **⚠️ 재배포 effect**: `common_schemas` 버전이 올랐으면 소비 서비스(`api_server`/`worker`/`execution_engine`/`agent-composer`/`frontend`) 재배포 필요 명시. env/secret 신규는 terraform apply 필요([[deploy_image_only_terraform_owns_env]]).
3. **⛔ 수동 재시드**: 시드 JSON(`database/seeds/node_definitions.json`, `modules/ai_agent/seeds/**`) 변경이 포함됐는지 `git diff --name-only origin/release origin/development | grep -E "seeds/"`로 확인. 있으면 **CI에 seed 자동화가 없으므로** staging `node_definitions` 수동 재시드 절차를 본문에 적는다([[staging_node_catalog_reseed]] — cloud-sql-proxy `--port 6544`, `ssl=False`, IAM 내 계정). 없으면 "시드 변경 없음" 명시.
4. **머지 방법 권고**: 가능하면 **merge commit(스쿼시 금지)** — 그래야 development가 release의 조상이 돼 다음 sync의 baseline 충돌이 끊긴다. (스쿼시만 허용되는 repo면 `-s ours` 덕에 이번 PR은 충돌 0이지만 다음에도 이 커맨드로 반복.)

## Step 3. 생성 (push + PR — 사전 확인 필수)

1. Step 0~2 결과(안전성 판정 + 트리 diff 규모 + 본문 초안)를 **채팅에 먼저 제시**.
2. 사용자 확인 후 push + PR:
   ```bash
   git push -u origin chore/release-sync-$DATE
   gh pr create --base release --head chore/release-sync-$DATE \
     --title "chore(release-sync): development → release 동기화 ($DATE)" --body-file <file>
   ```
3. mergeable 확인: `gh pr view <N> --json mergeable -q .mergeable` → **MERGEABLE**(UNSTABLE은 CI 진행중일 뿐 충돌 아님). CONFLICTING이면 Step 0의 release-only 가정이 깨진 것 → 재점검.

> 머지 클릭은 사용자(황대원) 권한 — Claude는 절대 머지하지 않는다. release-sync도 동일.
