# Gemini Web Operator — Phiên liên tục theo từng tập Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Giữ một Chrome Gemini Web visible và một conversation URL duy nhất cho toàn bộ một tập, để người dùng tự đăng nhập/chọn model còn Antigravity gửi packet, trao đổi follow-up có giới hạn và nhận bằng chứng thật.

**Architecture:** `GeminiSessionRegistry` lưu PID/debugger/conversation cho đúng run trong `.local/`; Selenium chỉ chờ và đọc account/model/mode do người dùng chọn, không tự bấm đổi model. `gemini-web run` khởi động hoặc attach session và gửi lượt đầu; `gemini-web continue` gửi follow-up trong cùng chat; `gemini-web stop` dọn process sau FINAL. Operator giữ receipt/ledger fail-closed và Antigravity chỉ gọi các lệnh engine.

**Tech Stack:** Python 3.13, Selenium WebDriver, Chrome remote debugging visible, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-08-30-gemini-web-phien-lien-tuc-design.md`

## Global Constraints

- Một run chỉ phục vụ một anime/mùa/tập và một Chrome profile riêng `.local/gemini_ultra_chrome/`.
- Người dùng tự đăng nhập Ultra và tự chọn `3.7 Flash` + `Tư duy mở rộng`; operator chỉ đọc DOM, không đổi model/mode.
- Không dùng Gemini API, MCP dự phòng, Chrome profile thường, password/cookie export, nhiều tài khoản hoặc fallback model.
- Antigravity không được tạo `raw_response`, critic, screenshot, receipt hay verdict PASS thủ công.
- Mỗi phase tối đa 6 lượt trong cùng conversation; hết lượt hoặc lỗi browser thì giữ cửa sổ để người dùng xử lý và dừng fail-closed.
- Chỉ FINAL PASS mới gọi cleanup; lỗi human không đóng Chrome và không xóa metadata phiên.
- TTS/video pipeline và source video không bị sửa trong thay đổi này.

### Task 1: Khóa hợp đồng DOM cho setup thủ công

**Files:**
- Modify: `src/anime_review_mvp/gemini_selenium.py` (`ACCOUNT_SELECTORS`, `SeleniumGeminiPage`, `run_gemini_session`)
- Test: `tests/unit/test_gemini_selenium.py`

**Interfaces:**
- Produces `BrowserReadiness(account: AccountObservation, model_label: str, mode_label: str)` and `SeleniumGeminiPage.wait_until_ready(policy: OperatorPolicy) -> BrowserReadiness`.
- `verify_account()` waits for a human login and returns only after email + Ultra are visible; it raises `GeminiBrowserError("LOGIN_REQUIRED", ...)` or `"ACCOUNT_MISMATCH"` without closing the driver.
- Adds `open_conversation(url: str) -> None`; `open_new_chat()` remains first-turn-only.
- Removes production calls to `select_model()`/`select_mode()`; retain them only if existing unit tests need backward compatibility.

- [ ] **Step 1: Write failing tests for manual readiness.** Add a fake page/driver where the account selector is initially absent, then becomes available, and where active model/mode text is already `3.7 Flash`/`Tư duy mở rộng`; assert `wait_until_ready()` returns without any click on model controls. Add a wrong-model test asserting `MODEL_NOT_FOUND` and that no upload/send occurs.
- [ ] **Step 2: Run the focused tests and verify they fail.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_gemini_selenium.py -k "ready or generic_account" -q
```

Expected: FAIL because the current adapter only searches three account selectors and auto-selects model/mode.

- [ ] **Step 3: Implement robust account polling and DOM observation.** Keep the generic case-insensitive account selectors and the 180-second human-login wait. Add active-label readers that inspect visible model/mode controls without clicking them, require exact normalized labels, and add `open_conversation()` with a real `/app/<chat-id>` URL check. Make `run_gemini_session()` call `open_new_chat()` only when no conversation URL was supplied.
- [ ] **Step 4: Run the focused tests and lint.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_gemini_selenium.py -q
.venv\Scripts\ruff.exe check src/anime_review_mvp/gemini_selenium.py tests/unit/test_gemini_selenium.py
```

Expected: PASS with no model/mode selection click in the new path.

- [ ] **Step 5: Commit the DOM contract.**

```powershell
git add src/anime_review_mvp/gemini_selenium.py tests/unit/test_gemini_selenium.py
git commit -m "fix: wait for manual Gemini Web readiness"
```

### Task 2: Add a persistent per-run browser registry

**Files:**
- Create: `src/anime_review_mvp/gemini_session.py`
- Modify: `src/anime_review_mvp/gemini_selenium.py`
- Test: `tests/unit/test_gemini_session.py`, `tests/unit/test_gemini_selenium.py`

**Interfaces:**
- `GeminiSessionMetadata(run_id: str, chrome_pid: int, debugger_address: str, conversation_url: str | None, started_at: str, phase_turns: dict[str, int])`.
- `GeminiSessionRegistry(path: Path)` with `load()`, `save(metadata)`, `clear(run_id)`, `assert_attachable(run_id)`, and `increment_turn(run_id, phase) -> int`.
- `connect_managed_chrome(metadata) -> ChromeLaunch` attaches Selenium to the saved debugger address; `ChromeLaunch.detach()` quits only the WebDriver, while `ChromeLaunch.close()` terminates Chrome and releases all registry state.

- [ ] **Step 1: Write failing registry tests.** Cover save/load round-trip, run-ID mismatch, stale debugger endpoint, turn counter rejecting the seventh turn, and `clear()` deleting only the session metadata file.
- [ ] **Step 2: Run the new tests and verify RED.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_gemini_session.py -q
```

- [ ] **Step 3: Implement the registry and attach path.** Store only run ID, PID, debugger address, conversation URL and counters in `.local/gemini_operator_session.json`; verify `/json/version` and PID before attach, reject another run, and treat dead metadata as stale. Correct both CLI call sites to pass the project root to `launch_managed_chrome(root)`, producing exactly `root/.local/gemini_ultra_chrome` rather than the accidental `.local/.local` path.
- [ ] **Step 4: Add lifecycle tests.** Assert a successful non-final operation calls `detach()` and leaves Chrome/metadata alive, while `close()` terminates the process and removes the registry. Use fakes; do not launch real Chrome in unit tests.
- [ ] **Step 5: Run focused tests and commit.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_gemini_session.py tests/unit/test_gemini_selenium.py -q
git add src/anime_review_mvp/gemini_session.py src/anime_review_mvp/gemini_selenium.py tests/unit/test_gemini_session.py tests/unit/test_gemini_selenium.py
git commit -m "feat: persist Gemini browser session per run"
```

### Task 3: Continue one conversation across phases

**Files:**
- Modify: `src/anime_review_mvp/gemini_selenium.py`, `src/anime_review_mvp/gemini_operator.py`, `src/anime_review_mvp/gemini_web.py`
- Test: `tests/unit/test_gemini_selenium.py`, `tests/unit/test_gemini_operator_transaction.py`, `tests/unit/test_gemini_web.py`

**Interfaces:**
- `BrowserTurn(index: int, prompt_sha256: str, response_sha256: str, conversation_url: str, started_at: str, finished_at: str)`.
- `BrowserConversationResult(observation: BrowserObservation, response: str, turns: tuple[BrowserTurn, ...])`.
- `run_gemini_session(..., conversation_url: str | None, prompt: str, upload_paths: tuple[Path, ...]) -> BrowserConversationResult` updates the registry with the single conversation URL and records one turn.
- `run_operator_phase(..., prompt_override: Path | None = None)` attaches to the registry URL for later phases; it does not create a new chat.

- [ ] **Step 1: Add failing fake-browser tests.** Run SCRIPT then PROXY with the same registry and assert the second call invokes `open_conversation()` with the first URL and never invokes `open_new_chat()`. Assert the response envelope contains turn hashes and the receipt still validates.
- [ ] **Step 2: Run the tests and verify RED.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_gemini_selenium.py tests/unit/test_gemini_operator_transaction.py -k "conversation or turn" -q
```

- [ ] **Step 3: Implement conversation persistence.** Pass the registry into the browser session runner, select new-chat vs existing-chat from `conversation_url`, increment the phase counter before sending, and save `conversation_url` under `run/gemini_web/session.json` as well as `.local` metadata. Include the turns in `raw_response.json` and bind the final URL/turn count into `OperatorReceipt` without weakening existing HMAC/hash checks.
- [ ] **Step 4: Update loading/verification.** Make `load_operator_verified_review()` reject a receipt whose conversation URL differs from `session.json`, whose turn count is zero, or whose URL is the bare `/app`; retain all existing packet and artifact hash checks.
- [ ] **Step 5: Run focused tests and commit.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_gemini_selenium.py tests/unit/test_gemini_operator_transaction.py tests/unit/test_gemini_web.py -q
git add src/anime_review_mvp/gemini_selenium.py src/anime_review_mvp/gemini_operator.py src/anime_review_mvp/gemini_web.py tests
git commit -m "feat: reuse one Gemini conversation across phases"
```

### Task 4: Add bounded follow-up turns for Antigravity

**Files:**
- Modify: `src/anime_review_mvp/cli.py`, `src/anime_review_mvp/gemini_operator.py`, `src/anime_review_mvp/gemini_selenium.py`
- Test: `tests/unit/test_cli_antigravity.py`, `tests/unit/test_gemini_operator.py`, `tests/unit/test_gemini_operator_transaction.py`

**Interfaces:**
- CLI adds `gemini-web continue --run <RUN> --phase <PHASE> --prompt-file <FILE>`; the prompt file must be inside the run and is read by the trusted operator only.
- `continue` creates a new nonce/request for the same phase and conversation, sends only the follow-up prompt, and writes a new signed receipt; it never uploads an unbound file or creates a new chat.
- `OperatorPolicy.max_turns = 6`; registry counters reject calls after six turns with `CONVERSATION_TURN_LIMIT`.
- Follow-up receipts keep raw response separate from normalized critic and retain all existing fail-closed checks.

- [ ] **Step 1: Write failing tests.** Test parser acceptance/rejection of `continue`, prompt path containment, same conversation URL, seventh-turn rejection, and that a follow-up response with invalid JSON never creates a critic or PASS.
- [ ] **Step 2: Run tests and verify RED.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_cli_antigravity.py tests/unit/test_gemini_operator.py tests/unit/test_gemini_operator_transaction.py -k "continue or turn_limit" -q
```

- [ ] **Step 3: Implement the command and transaction.** Add the action to the parser, load the active registry/session, issue a fresh request bound to the phase packet, send the prompt through Selenium, append a turn record, parse/validate the final JSON and sign a new receipt. On all `GeminiBrowserError`s, leave Chrome and metadata alive and mark the specific human-required code.
- [ ] **Step 4: Run focused tests and commit.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_cli_antigravity.py tests/unit/test_gemini_operator.py tests/unit/test_gemini_operator_transaction.py -q
git add src/anime_review_mvp/cli.py src/anime_review_mvp/gemini_operator.py src/anime_review_mvp/gemini_selenium.py tests
git commit -m "feat: allow bounded Gemini follow-up turns"
```

### Task 5: Make browser lifecycle visible and safe in the CLI

**Files:**
- Modify: `src/anime_review_mvp/cli.py`, `src/anime_review_mvp/gemini_selenium.py`
- Test: `tests/unit/test_cli_antigravity.py`, `tests/acceptance/test_episode_pipeline.py`

**Interfaces:**
- `gemini-web run` starts/attaches a visible browser, prints the managed profile path and a clear instruction to log in/select model, then waits instead of closing on `LOGIN_REQUIRED` or `MODEL_NOT_FOUND`.
- `gemini-web stop --run <RUN>` closes the registered Chrome process and removes only `.local/gemini_operator_session.json`/lock metadata.
- FINAL success calls the same cleanup path after `_accept_operator_review()` returns 0; PROXY/SCRIPT success detaches the WebDriver but keeps Chrome alive.

- [ ] **Step 1: Write failing CLI lifecycle tests.** Fake `ChromeLaunch` and assert `run_operator_phase` passes the project root, calls `detach` on non-final/error paths, `stop` calls `close`, and the parser exposes `stop` without changing the existing run syntax.
- [ ] **Step 2: Run tests and verify RED.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_cli_antigravity.py tests/acceptance/test_episode_pipeline.py -k "browser or stop or lifecycle" -q
```

- [ ] **Step 3: Implement lifecycle behavior.** Remove unconditional `finally: launch.close()` from phase execution; use `detach` while preserving the registry. Add explicit stop and final-pass cleanup, and make stale metadata recoverable. Do not touch the user's normal Chrome profile.
- [ ] **Step 4: Run acceptance tests and commit.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_cli_antigravity.py tests/acceptance/test_episode_pipeline.py -q
git add src/anime_review_mvp/cli.py src/anime_review_mvp/gemini_selenium.py tests
git commit -m "fix: keep Gemini browser visible for human setup"
```

### Task 6: Update Antigravity instructions and smoke documentation

**Files:**
- Modify: `Bo_nao_Antigravity/GEMINI.md`, `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md`
- Create: `docs/gemini-web-smoke.md`
- Test: `tests/unit/test_antigravity_contract.py`

**Interfaces:**
- Policy states that the user manually logs in/selects `3.7 Flash` + `Tư duy mở rộng`, engine only observes, and `gemini-web continue` is the only follow-up path.
- Policy states SCRIPT/PROXY/FINAL share one conversation URL per run and Chrome remains open on human-required errors.
- Smoke guide gives exact PowerShell commands, expected visible actions, and the one manual action (login/model selection); it does not contain credentials.

- [ ] **Step 1: Add failing contract assertions.** Require `gemini-web continue`, `gemini-web stop`, `wait for manual`, `same conversation`, and forbid phrases that claim engine auto-selects model or opens a new chat per phase.
- [ ] **Step 2: Implement policy and smoke guide.** Update only instructions/docs; keep Antigravity’s no-source/no-brain-edit/write-policy restrictions unchanged.
- [ ] **Step 3: Run contract tests and commit.**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_antigravity_contract.py -q
git add Bo_nao_Antigravity/GEMINI.md Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md docs/gemini-web-smoke.md tests/unit/test_antigravity_contract.py
git commit -m "docs: direct Antigravity through persistent Gemini chat"
```

### Task 7: Full verification and real-browser handoff

**Files:**
- No new implementation files; verify all changed files above.

- [ ] **Step 1: Run the complete automated suite.**

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check src tests
```

Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 2: Run the mandatory manual smoke only after the user is ready.** From the project root, use the smoke guide with a tiny packet. Confirm visibly: dedicated Chrome opens, user logs in/selects model, operator waits, upload/send occurs, response appears, a follow-up remains in the same chat, and the chat is visible in Gemini history. Do not run the full BLACK TORCH episode yet.
- [ ] **Step 3: Record smoke evidence.** Save the real screenshot/conversation URL under the smoke run; never substitute a generated image or hand-written receipt.
- [ ] **Step 4: Report exact status.** Include test output, profile/session paths, whether smoke passed, and any human-required code. Do not claim the BLACK TORCH video is fixed until a new revision is actually run and audited.

## Execution order

Run Tasks 1–7 in order. Tasks 1–6 each end with a focused test/commit; Task 7 is the final verification gate. Do not open a real Gemini window before Tasks 1–6 pass. Do not merge this worktree into `feature/anime-review-mvp` until verification and user review are complete.
