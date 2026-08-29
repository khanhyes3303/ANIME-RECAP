# Gemini Ultra Web Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bắt buộc mọi kiểm định kịch bản, proxy và final đi qua đúng phiên Gemini Web Ultra có bằng chứng, rồi chỉ publish khi toàn bộ beat đạt.

**Architecture:** Engine tạo evidence và request có hash; Antigravity Browser Agent chỉ vận chuyển request tới Gemini Web và lưu nguyên phản hồi/bằng chứng. Engine xác thực receipt, schema, dependency hash và verdict; không có Ultra receipt hợp lệ thì fail-closed. Artifact thay đổi theo revision được gắn fingerprint để dữ liệu cũ không thể qua cổng mới.

**Tech Stack:** Python 3.13, dataclasses, strict JSON loader, SHA-256, FFmpeg, pytest, Ruff, Antigravity Browser Agent, Gemini Web Ultra.

**Spec:** `docs/superpowers/specs/2026-08-29-gemini-ultra-web-verifier-design.md`

## Global Constraints

- Chỉ dùng Gemini Web với tài khoản Google Ultra của người dùng; không Gemini API, không fallback model/account.
- Browser Agent dùng profile Chrome riêng; người dùng tự đăng nhập, engine không đọc hoặc lưu password/cookie.
- Sai tài khoản, thiếu chữ `Ultra` trong plan label, không xác nhận mode mạnh nhất, CAPTCHA, upload lỗi hoặc receipt sai đều dừng.
- Codex chỉ sửa engine/test/docs; không render tập BLACK TORCH và không sửa video nguồn hay `Kho_Anime` trong lúc triển khai.
- Antigravity không được sửa `Bo_nao_Antigravity`, `src`, `tests`, `docs`, dependency hoặc Git.
- Mỗi thay đổi production phải có test RED được quan sát trước.
- Không cài MCP hoặc dependency mới; Browser Agent tích hợp là đường duy nhất.

---

### Task 1: Hợp đồng request và Ultra receipt

**Files:**
- Create: `src/anime_review_mvp/gemini_web.py`
- Create: `tests/unit/test_gemini_web.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `GeminiUltraProfileBinding`, `GeminiWebRequest`, `GeminiUltraSessionReceipt`, `GeminiWebReceipt`, `sha256_file(path)`, `load_verified_web_review(run_dir, phase, review_cls)`.
- Consumes: strict `load_json`, `MvpError`, paths nằm trong một run.

- [ ] **Step 1: Viết test RED cho receipt đúng Ultra và đúng hash request/response**

```python
def test_receipt_requires_ultra_and_exact_request_response_hashes(tmp_path: Path) -> None:
    request_path, response_path, screenshot = write_web_fixture(tmp_path)
    receipt = GeminiWebReceipt(
        "FINAL", sha256_file(request_path), sha256_file(response_path),
        str(response_path), (str(screenshot),),
        GeminiUltraSessionReceipt(
            binding.account_sha256, "kh***@gmail.com", "Google AI Ultra",
            "Deep Think", True, "READY"
        ),
    )
    assert verify_receipt(tmp_path, receipt, request_path).phase == "FINAL"
```

- [ ] **Step 2: Chạy `uv run pytest tests/unit/test_gemini_web.py -v` và xác nhận import/function chưa tồn tại.**

- [ ] **Step 3: Cài dataclass strict và kiểm tra fail-closed**

```python
@dataclass(frozen=True, slots=True)
class GeminiUltraSessionReceipt:
    account_sha256: str
    account_hint: str
    plan_label: str
    model_label: str
    strongest_mode_confirmed: bool
    browser_status: str

    def __post_init__(self) -> None:
        if "ultra" not in self.plan_label.casefold():
            raise MvpError("Gemini Web session is not Google AI Ultra")
        if self.browser_status != "READY":
            raise MvpError("Gemini Web browser session is not ready")
        if not self.strongest_mode_confirmed or not self.model_label.strip():
            raise MvpError("Gemini Web strongest mode is not confirmed")
```

`verify_receipt(...)` phải resolve mọi response/screenshot dưới đúng `run_dir`, tính lại SHA-256, yêu cầu ít nhất một screenshot, request ID/phase trùng và từ chối symlink/path thoát run.

`GeminiUltraProfileBinding` nằm trong `.local/gemini_ultra_profile.json` đã gitignore,
chỉ chứa `account_sha256` và `account_hint` đã che. Lệnh enroll nhận email đang hiển
thị từ Browser Agent qua stdin, chuẩn hóa/calculate SHA-256 trong tiến trình rồi bỏ
chuỗi gốc; receipt mỗi lượt phải có fingerprint trùng binding.

Thêm chính xác `/.local/` vào `.gitignore`; test phải xác nhận file binding không
được `git check-ignore` bỏ sót.

- [ ] **Step 4: Thêm test RED rồi GREEN cho account fingerprint khác binding, tài khoản thường, `browser_status` khác `READY`, hash sai, screenshot thiếu và path ngoài run.**

- [ ] **Step 5: Chạy `uv run pytest tests/unit/test_gemini_web.py -v` và commit `feat: add fail-closed Gemini Ultra receipts`.**

### Task 2: Evidence dày và contact sheet do engine sở hữu

**Files:**
- Modify: `src/anime_review_mvp/models.py`
- Modify: `src/anime_review_mvp/media.py`
- Modify: `tests/unit/test_media.py`

**Interfaces:**
- Produces: `DenseFrame`, `DenseEvidenceDocument`, `ContactSheetDocument`, `extract_dense_beat_evidence(video, storyboard, edl, output_dir, timeline, max_gap_ms=1_000, runner=subprocess.run)`.
- Consumes: `AtomicStoryboard`, optional `SpanEdlDocument`, FFmpeg runner.

- [ ] **Step 1: Viết test RED đảm bảo khoảng cách mẫu không vượt 1.000 ms và luôn có start/action-start/action-end/end.**

```python
def test_dense_evidence_covers_boundaries_and_action_window(tmp_path: Path) -> None:
    evidence = extract_dense_beat_evidence(
        source, storyboard(), None, tmp_path / "dense", "SOURCE", runner=fake_runner
    )
    stamps = [frame.timestamp_ms for frame in evidence.frames if frame.beat_id == "beat-001"]
    assert {1_000, 1_500, 2_700, 4_000} <= set(stamps)
    assert max(b - a for a, b in pairwise(stamps)) <= 1_000
```

- [ ] **Step 2: Chạy test và xác nhận fail vì mới có ba anchor START/MIDDLE/END.**

- [ ] **Step 3: Cài sampling deterministic, frame filenames chứa beat/timeline/timestamp và manifest ghi SHA-256 từng JPEG.**

- [ ] **Step 4: Dùng FFmpeg ghép tối đa 12 frame/contact sheet, tạo nhiều sheet khi beat dài; overlay nhãn `beat_id`, timeline và timestamp. Không thêm Pillow.**

- [ ] **Step 5: Thêm test cho PROGRAM timestamp lấy từ EDL, sheet pagination và FFmpeg failure; chạy `uv run pytest tests/unit/test_media.py -v`.**

- [ ] **Step 6: Commit `feat: generate dense beat evidence for web verification`.**

### Task 3: Bundle kiểm định có hash và ba phase độc lập

**Files:**
- Modify: `src/anime_review_mvp/gemini_web.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `tests/unit/test_cli_antigravity.py`

**Interfaces:**
- CLI mới: `web-verify enroll|prepare|accept`; `prepare|accept` nhận `--run PATH --phase script|proxy|final`, còn `enroll` tạo binding tài khoản một lần sau khi người dùng xác nhận đúng account Ultra.
- Produces trong run: `gemini_web/<phase>/request.json`, `prompt.txt`, `response.txt`, `receipt.json`, `screenshots/`, `critic_<phase>.json`.

- [ ] **Step 1: Viết parser test RED cho ba action và ba phase.**

```python
def test_web_verify_parser_requires_action_run_and_phase() -> None:
    args = cli._parser().parse_args(
        ["web-verify", "prepare", "--run", "run", "--phase", "final"]
    )
    assert (args.action, args.phase) == ("prepare", "final")
```

- [ ] **Step 2: Viết test RED: prepare tạo request từ đúng storyboard, script, evidence và final candidate; request ID là SHA-256 của canonical payload.**

- [ ] **Step 3: Cài `build_web_request(...)` và prompt tiếng Việt yêu cầu JSON-only với verdict `MATCH`, `VOICE_EARLY`, `VOICE_LATE`, `WRONG_VISUAL`, `EXCLUDED_CONTENT`, `UNCERTAIN`.**

- [ ] **Step 4: Viết test RED: accept từ chối receipt của phase khác, fingerprint tài khoản khác binding, review thiếu beat, evidence hash cũ và model không phải Ultra/strongest.**

- [ ] **Step 5: Cài accept: kiểm receipt trước rồi mới load `CriticReviewDocument`; chuyển các verdict web sang verdict nội bộ, trong đó chỉ `MATCH` không sinh finding.**

- [ ] **Step 6: Chạy `uv run pytest tests/unit/test_cli_antigravity.py tests/unit/test_gemini_web.py -v` và commit `feat: add Gemini Web verification bundle CLI`.**

### Task 4: Gắn Ultra gate vào workflow, tách proxy khỏi final

**Files:**
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/audit.py`
- Modify: `tests/unit/test_workflow.py`
- Modify: `tests/unit/test_atomic_edl_audit.py`
- Modify: `tests/unit/test_cli_antigravity.py`

**Interfaces:**
- New stages: `CHO_GEMINI_SCRIPT`, `CHO_GEMINI_PROXY`, `CHO_GEMINI_FINAL`.
- Final audit consumes `gemini_web/final/critic_final.json` và ba receipt hợp lệ; không dùng lại `Bao_cao/critic_video.json` của proxy.

- [ ] **Step 1: Viết transition tests RED cho storyboard → Gemini script → TTS → proxy → Gemini proxy → final → Gemini final → engine audit.**

- [ ] **Step 2: Cài stage transitions và `next_action.json` chỉ rõ lệnh `web-verify prepare` hoặc Browser Agent cần chạy.**

- [ ] **Step 3: Viết regression RED chứng minh proxy review `MATCH` nhưng final review `VOICE_EARLY` vẫn không thể publish.**

- [ ] **Step 4: Sửa `_audit_atomic_engine(...)` chỉ đọc final critic/receipt đã xác thực; yêu cầu stage metrics cho cả ba lượt Gemini Web.**

- [ ] **Step 5: Viết test RED: thiếu session screenshot, `browser_status` là `CAPTCHA`, `UNCERTAIN`, thiếu một beat, account fingerprint sai hoặc plan không chứa Ultra đều đưa run tới `CAN_CON_NGUOI_XU_LY`, không tạo `review_anime.mp4`.**

- [ ] **Step 6: Chạy `uv run pytest tests/unit/test_workflow.py tests/unit/test_atomic_edl_audit.py tests/unit/test_cli_antigravity.py -v` và commit `feat: require Ultra verification before publish`.**

### Task 5: Revision fingerprint chặn tài nguyên cũ

**Files:**
- Modify: `src/anime_review_mvp/workspace.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/gemini_web.py`
- Modify: `tests/unit/test_workspace.py`
- Modify: `tests/unit/test_cli_antigravity.py`

**Interfaces:**
- Produces: `ArtifactFingerprint(name, sha256, dependency_sha256, run_id)` và `run_manifest.json` trong run.
- Consumes: source hash, policy hash, storyboard/script/TTS/EDL/evidence/final hashes.

- [ ] **Step 1: Viết test RED: revision mới dùng receipt/contact sheet/critic từ run trước phải bị từ chối dù đường dẫn episode giống nhau.**

- [ ] **Step 2: Cài run ID và dependency chain:**

```text
storyboard <- source + policy
script receipt <- storyboard + SOURCE evidence
TTS <- narration text + voice ID
EDL <- storyboard + TTS durations
proxy receipt <- proxy + SOURCE/PROGRAM evidence + script
final receipt <- final candidate + SOURCE/PROGRAM evidence + script
publish <- final receipt + engine audit
```

- [ ] **Step 3: Chỉ reuse transcript/shots/source frames khi source SHA-256 giống; không reuse critic/contact sheet/TTS/EDL/final khi dependency fingerprint đổi.**

- [ ] **Step 4: Viết test RED: final candidate giống hệt final cũ trong revision có input thay đổi phải bị `STALE_FINAL_REUSED`; input không đổi được phép tạo cùng hash nhưng vẫn phải có receipt mới mang run ID mới.**

- [ ] **Step 5: Chạy `uv run pytest tests/unit/test_workspace.py tests/unit/test_cli_antigravity.py -v` và commit `fix: isolate revision verification artifacts`.**

### Task 6: Chỉ dẫn Browser Agent và mẫu artifact

**Files:**
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Modify: `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md`
- Create: `Bo_nao_Antigravity/mau/gemini_ultra_session_receipt.json`
- Create: `Bo_nao_Antigravity/mau/gemini_web_receipt.json`
- Create: `Bo_nao_Antigravity/mau/critic_final.json`
- Modify: `README.md`
- Modify: `tests/unit/test_antigravity_contract.py`

**Interfaces:**
- Antigravity Browser Agent consumes `gemini_web/<phase>/prompt.txt` và request bundle.
- Antigravity must produce raw web response, screenshots, receipt and strict critic JSON only at engine-declared paths.

- [ ] **Step 1: Viết contract tests RED chạy `render_operator_prompt(...)`, xác nhận prompt đầu ra buộc ba phase Ultra và không còn placeholder.**

```python
def test_rendered_operator_prompt_requires_all_ultra_web_phases(tmp_path: Path) -> None:
    rendered = render_operator_prompt(tmp_path / "run", prompt_template)
    for phase in ("script", "proxy", "final"):
        assert f"web-verify prepare --phase {phase}" in rendered
        assert f"web-verify accept --phase {phase}" in rendered
    assert "<ĐƯỜNG_DẪN_RUN>" not in rendered
```

- [ ] **Step 2: Cập nhật brain: mở profile riêng; lần đầu người dùng login và xác nhận đúng account Ultra rồi chạy `web-verify enroll`; trước mỗi phase so fingerprint/plan/model, tạo chat mới, upload đúng bundle, lưu nguyên response và screenshot.**

- [ ] **Step 3: Ghi rõ Browser Agent không được tự gõ verdict thay Gemini Web, không được bỏ qua CAPTCHA/login, không được báo PASS bằng markdown.**

- [ ] **Step 4: Cập nhật prompt một lần chạy và README với đúng chuỗi lệnh; chỉ một đường Ultra, không nhắc API/MCP/fallback.**

- [ ] **Step 5: Chạy `uv run pytest tests/unit/test_antigravity_contract.py -v` và commit `docs: direct Antigravity through Gemini Ultra Web`.**

### Task 7: Acceptance, fail-closed và kiểm tra toàn bộ

**Files:**
- Modify: `tests/acceptance/test_episode_pipeline.py`
- Modify: fixtures dưới `tests/fixtures/operator_artifacts/` nếu schema yêu cầu.

**Interfaces:**
- Acceptance flow: storyboard → dense SOURCE → Ultra script receipt → TTS/EDL → proxy → Ultra proxy receipt → final → Ultra final receipt → engine audit → publish.

- [ ] **Step 1: Viết acceptance RED cho một run sạch có ba receipt/hashes khác nhau và toàn bộ beat `MATCH`.**

- [ ] **Step 2: Viết regression RED mô phỏng BLACK TORCH: title card lọt giữa beat, Gemini final trả `EXCLUDED_CONTENT`; xác nhận không publish.**

- [ ] **Step 3: Viết regression RED cho response cũ được copy sang revision mới; xác nhận request hash/run ID chặn nó.**

- [ ] **Step 4: Chạy `uv run pytest -q`; expected: toàn bộ test PASS.**

- [ ] **Step 5: Chạy `uv run ruff check .` và `git diff --check`; expected: exit code 0.**

- [ ] **Step 6: Kiểm tra `git status --short` để xác nhận không có thay đổi trong `Kho_Anime`, video nguồn hoặc `Tam_dang_xu_ly`; commit `test: verify Gemini Ultra fail-closed pipeline`.**

## Self-Review Result

- Spec coverage: Ultra-only, profile riêng, xác nhận strongest mode, ba phase web, raw response/screenshot/hash, fail-closed, dense evidence và revision isolation đều có task/test tương ứng.
- Placeholder scan: không có TBD/TODO/“implement later”; mọi bước production nêu interface và test kiểm chứng.
- Type consistency: `GeminiUltraProfileBinding`, `GeminiWebRequest`, `GeminiUltraSessionReceipt`, `GeminiWebReceipt`, `DenseEvidenceDocument` và `ArtifactFingerprint` chỉ có một tên xuyên suốt.
- Boundary: không thêm API, MCP hay dependency; Browser Agent là phần vận chuyển UI, engine là bên duy nhất quyết định PASS/publish.
