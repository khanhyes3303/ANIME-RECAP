# Gemini Web Operator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây một operator cục bộ mở Chrome thật, khóa `3.7 Flash + Tư duy mở rộng`, tải packet kiểm định lên Gemini Web và chỉ cấp receipt khi có phiên web thật hợp lệ.

**Architecture:** Engine tạo packet và request có nonce; `GeminiWebOperator` khởi động Chrome chuyên dụng qua remote debugging, Selenium thao tác UI và thu phản hồi DOM. Operator ghi ledger HMAC ngoài run; engine chỉ chấp nhận receipt có ledger tương ứng, bằng chứng ảnh hợp lệ và đúng model/account. Antigravity chỉ gọi `gemini-web run`, không còn đường tự nộp critic hoặc receipt.

**Tech Stack:** Python 3.12+, pytest, Selenium 4, Chrome/ChromeDriver, Pillow, FFmpeg/FFprobe, HMAC-SHA256, JSONL ledger.

**Spec:** `docs/superpowers/specs/2026-08-29-gemini-web-operator-design.md`

## Global Constraints

- Chỉ một profile Chrome tại `.local/gemini_ultra_chrome/`; không dùng profile Chrome mặc định.
- Model bắt buộc là `3.7 Flash`; mode bắt buộc là `Tư duy mở rộng`; plan phải chứa `Ultra`.
- Người dùng tự đăng nhập; code không đọc hoặc lưu mật khẩu/cookie.
- Không Gemini API, MCP, browser dự phòng, model dự phòng hoặc receipt nhập thủ công.
- Browser phải hữu hình; `headless` luôn bị cấm.
- Sai browser/account/model/upload/response/bằng chứng phải dừng, không render tiếp.
- Mỗi phase tạo một chat Gemini thật và conversation URL riêng.
- Run revision BLACK TORCH đầu tiên sau thay đổi phải bỏ toàn bộ TTS/EDL/proxy/critic/final cũ.
- Không chạy lại toàn tập trước khi smoke test Chrome thật và packet nhỏ PASS.

---

## File Structure

- `src/anime_review_mvp/gemini_operator.py`: contract request/observation/receipt, nonce, HMAC ledger và kiểm định provenance.
- `src/anime_review_mvp/gemini_selenium.py`: khởi động Chrome chuyên dụng, thao tác Gemini DOM, upload và thu phản hồi.
- `src/anime_review_mvp/gemini_packets.py`: tạo packet bất biến cho `SCRIPT`, `PROXY`, `FINAL`.
- `src/anime_review_mvp/gemini_web.py`: giữ request/evidence hashing và chuyển sang chỉ nhận receipt đã được operator xác thực.
- `src/anime_review_mvp/cli.py`: thay `web-verify prepare|accept` bằng `gemini-web enroll|smoke|run`.
- `src/anime_review_mvp/tts.py`: đưa `revision_id` và source hash vào cache key.
- `src/anime_review_mvp/workflow.py`: trạng thái lỗi browser cụ thể và cổng dừng.
- `Bo_nao_Antigravity/GEMINI.md`: Antigravity chỉ gọi CLI operator, không tự tạo artifact web.
- `PROMPT_MOT_LAN_CHAY.md`: prompt một lần chạy theo CLI mới.
- `tests/unit/test_gemini_operator.py`: provenance, ảnh giả, HMAC, nonce và model policy.
- `tests/unit/test_gemini_selenium.py`: chuỗi hành động browser qua adapter giả ở ranh giới Selenium.
- `tests/unit/test_gemini_packets.py`: packet phase, hash và vùng cấm.
- `tests/unit/test_tts.py`: revision cache isolation.
- `tests/unit/test_cli_antigravity.py`: loại bỏ manual accept và fail-closed CLI.
- `tests/acceptance/test_episode_pipeline.py`: pipeline chỉ tiến stage sau operator receipt hợp lệ.
- `tests/manual/gemini_web_smoke.py`: smoke test Chrome thật, không chạy trong pytest mặc định.

---

### Task 1: Contract provenance và chặn đúng vụ giả mạo đã xảy ra

**Files:**
- Create: `src/anime_review_mvp/gemini_operator.py`
- Create: `tests/unit/test_gemini_operator.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `OperatorPolicy`, `OperatorRequest`, `BrowserObservation`, `OperatorReceipt`, `validate_browser_evidence()`.
- Consumes: `sha256_file()` và `account_sha256()` từ `gemini_web.py`.

- [ ] **Step 1: Thêm dependency và viết test thất bại tái hiện ảnh đen/model 2.5/response tự chế**

```python
def test_rejects_the_exact_fabricated_antigravity_evidence(tmp_path: Path) -> None:
    screenshot = tmp_path / "session.png"
    Image.new("RGB", (1280, 720), "black").save(screenshot)
    critic = tmp_path / "critic_script.json"
    raw = tmp_path / "response.txt"
    critic.write_text('{"overall_verdict":"MATCH"}', encoding="utf-8")
    raw.write_bytes(critic.read_bytes())
    observation = BrowserObservation(
        account_sha256="a" * 64,
        account_hint="n***@gmail.com",
        plan_label="Google AI Ultra",
        model_label="Gemini 2.5 Pro Ultra",
        mode_label="Tư duy mở rộng",
        conversation_url="https://gemini.google.com/app/abc",
        chrome_pid=123,
        screenshot_path=str(screenshot),
        started_at="2026-08-29T21:00:00+07:00",
        finished_at="2026-08-29T21:00:01+07:00",
    )
    with pytest.raises(MvpError, match="3.7 Flash|screenshot|raw response"):
        validate_browser_evidence(
            observation,
            OperatorPolicy.required(),
            raw_response=raw,
            critic=critic,
        )
```

Add to `pyproject.toml`:

```toml
"selenium>=4.35,<5",
"pillow>=11,<13",
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `uv run pytest tests/unit/test_gemini_operator.py::test_rejects_the_exact_fabricated_antigravity_evidence -v`

Expected: FAIL vì `anime_review_mvp.gemini_operator` chưa tồn tại.

- [ ] **Step 3: Viết contract và validation tối thiểu**

```python
@dataclass(frozen=True, slots=True)
class OperatorPolicy:
    model_label: str
    mode_label: str
    plan_token: str
    minimum_session_seconds: float

    @classmethod
    def required(cls) -> "OperatorPolicy":
        return cls("3.7 Flash", "Tư duy mở rộng", "Ultra", 3.0)

@dataclass(frozen=True, slots=True)
class BrowserObservation:
    account_sha256: str
    account_hint: str
    plan_label: str
    model_label: str
    mode_label: str
    conversation_url: str
    chrome_pid: int
    screenshot_path: str
    started_at: str
    finished_at: str

def validate_browser_evidence(
    observation: BrowserObservation,
    policy: OperatorPolicy,
    *,
    raw_response: Path,
    critic: Path,
) -> None:
    if observation.model_label != policy.model_label:
        raise MvpError(f"Gemini model must be {policy.model_label}")
    if observation.mode_label != policy.mode_label:
        raise MvpError(f"Gemini mode must be {policy.mode_label}")
    if policy.plan_token.casefold() not in observation.plan_label.casefold():
        raise MvpError("Gemini account is not Ultra")
    if raw_response.read_bytes() == critic.read_bytes():
        raise MvpError("raw response must differ from normalized critic")
    validate_session_screenshot(Path(observation.screenshot_path))
```

`validate_session_screenshot()` dùng Pillow để yêu cầu PNG/JPEG tối thiểu `1000x600`, có
ít nhất 32 màu trong ảnh thu nhỏ `160x90`, entropy grayscale tối thiểu `1.5` và kích
thước file tối thiểu `20_000` byte.

- [ ] **Step 4: Bổ sung test PASS và các trường hợp sai đơn lẻ**

Test riêng cho model sai, mode sai, plan không Ultra, URL `/app` trống, PID không dương,
phiên dưới ba giây, ảnh đồng màu và raw response trùng critic.

- [ ] **Step 5: Chạy test Task 1**

Run: `uv run pytest tests/unit/test_gemini_operator.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/anime_review_mvp/gemini_operator.py tests/unit/test_gemini_operator.py
git commit -m "feat: reject fabricated Gemini browser evidence"
```

---

### Task 2: Nonce dùng một lần và ledger HMAC ngoài run

**Files:**
- Modify: `src/anime_review_mvp/gemini_operator.py`
- Modify: `tests/unit/test_gemini_operator.py`

**Interfaces:**
- Consumes: `OperatorPolicy`, `BrowserObservation` từ Task 1.
- Produces: `OperatorRequest`, `OperatorReceipt`, `OperatorLedger`, `issue_request()`, `verify_operator_receipt()`.

- [ ] **Step 1: Viết test receipt tự tạo không có ledger phải RED**

```python
def test_receipt_without_matching_signed_ledger_entry_is_rejected(tmp_path: Path) -> None:
    ledger = OperatorLedger(tmp_path / "operator-ledger.jsonl", b"k" * 32)
    receipt = valid_receipt(nonce="nonce-not-recorded")
    with pytest.raises(MvpError, match="ledger"):
        verify_operator_receipt(receipt, ledger, expected_request=valid_request())
```

- [ ] **Step 2: Chạy test RED**

Run: `uv run pytest tests/unit/test_gemini_operator.py::test_receipt_without_matching_signed_ledger_entry_is_rejected -v`

Expected: FAIL vì ledger API chưa tồn tại.

- [ ] **Step 3: Cài đặt ledger append-only và HMAC canonical JSON**

```python
@dataclass(frozen=True, slots=True)
class OperatorRequest:
    run_id: str
    phase: str
    nonce: str
    request_sha256: str
    artifact_sha256: str
    packet_sha256: str
    issued_at: str

@dataclass(frozen=True, slots=True)
class OperatorReceipt:
    run_id: str
    phase: str
    nonce: str
    request_sha256: str
    artifact_sha256: str
    packet_sha256: str
    observation: BrowserObservation
    screenshot_sha256: str
    raw_response_path: str
    raw_response_sha256: str
    critic_path: str
    critic_sha256: str
    operator_build_sha256: str
    ledger_signature: str = ""

class OperatorLedger:
    def append(self, receipt: OperatorReceipt) -> str:
        if receipt.ledger_signature:
            raise MvpError("ledger only accepts unsigned operator receipts")
        payload = canonical_receipt_payload(receipt)
        signature = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        self._append_json_line({"payload": json.loads(payload), "signature": signature})
        return signature

    def verified_entry(self, nonce: str) -> OperatorReceipt:
        matches = self._verified_entries_for_nonce(nonce)
        if len(matches) != 1:
            raise MvpError("operator receipt has no unique ledger entry")
        receipt, signature = matches[0]
        return replace(receipt, ledger_signature=signature)
```

`canonical_receipt_payload()` loại duy nhất trường `ledger_signature`, giữ nguyên mọi
trường còn lại và serialize bằng UTF-8, `sort_keys=True`, separator `(',', ':')`.

Khóa 32 byte được tạo bằng `secrets.token_bytes(32)` tại
`.local/gemini_operator.key`; ledger tại `.local/gemini_operator_ledger.jsonl`. Cả hai
đều nằm ngoài run và đã được `.gitignore` bảo vệ.

- [ ] **Step 4: Test nonce tái dùng, signature sai, hash sai và entry trùng**

`verify_operator_receipt()` phải đối chiếu toàn bộ request hash, artifact hash, packet
hash, run, phase, nonce và receipt signature; nonce chỉ xuất hiện đúng một lần.

- [ ] **Step 5: Chạy test Task 2**

Run: `uv run pytest tests/unit/test_gemini_operator.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/anime_review_mvp/gemini_operator.py tests/unit/test_gemini_operator.py
git commit -m "feat: sign Gemini operator receipts in local ledger"
```

---

### Task 3: Chrome launcher và Selenium Gemini adapter hữu hình

**Files:**
- Create: `src/anime_review_mvp/gemini_selenium.py`
- Create: `tests/unit/test_gemini_selenium.py`

**Interfaces:**
- Consumes: `OperatorPolicy`, `BrowserObservation`.
- Produces: `ChromeLaunch`, `GeminiBrowserSession`, `launch_managed_chrome()`, `run_gemini_session()`.

- [ ] **Step 1: Viết test chuỗi hành động và cấm headless**

```python
def test_session_selects_required_model_mode_uploads_and_reads_real_url(tmp_path: Path) -> None:
    driver = RecordingDriver(
        account_email="nguyenkhanh@example.com",
        plan="Google AI Ultra",
        conversation_url="https://gemini.google.com/app/real-chat-id",
        response_text='{"phase":"SCRIPT","overall_verdict":"MATCH"}',
    )
    observation, response = run_gemini_session(
        driver,
        policy=OperatorPolicy.required(),
        account_hint="n***@example.com",
        expected_account_sha256=account_sha256("nguyenkhanh@example.com"),
        upload_paths=(tmp_path / "evidence.mp4", tmp_path / "manifest.json"),
        prompt="Return JSON only",
        screenshot_path=tmp_path / "session.png",
    )
    assert driver.events == [
        "open:new-chat", "verify:account", "select:3.7 Flash",
        "select:Tư duy mở rộng", "upload:2", "send", "wait:complete",
        "read:response", "screenshot",
    ]
    assert observation.conversation_url.endswith("real-chat-id")
    assert response.startswith("{")
```

- [ ] **Step 2: Chạy test RED**

Run: `uv run pytest tests/unit/test_gemini_selenium.py -v`

Expected: FAIL vì module chưa tồn tại.

- [ ] **Step 3: Cài đặt Chrome launcher có PID thật**

`launch_managed_chrome()`:

1. giữ khóa độc quyền `.local/gemini_operator.lock`; phiên thứ hai phải dừng trước khi mở Chrome;
2. tìm `chrome.exe` bằng `shutil.which()` rồi hai vị trí Program Files chuẩn;
3. lấy TCP port cục bộ trống;
4. dùng `subprocess.Popen` với remote-debugging port vừa cấp,
   profile `project_root / ".local" / "gemini_ultra_chrome"`, `--new-window` và URL Gemini;
5. tuyệt đối không thêm `--headless`;
6. chờ endpoint `/json/version` tại debugger address tối đa 30 giây;
7. attach Selenium bằng `ChromeOptions().debugger_address`;
8. trả `ChromeLaunch(driver, process.pid, debugger_address)` và giải phóng lock trong
   `finally` khi transaction kết thúc.

- [ ] **Step 4: Cài đặt adapter DOM fail-closed**

Tạo helper thử tuần tự selector đã khóa:

```python
MODEL_SELECTORS = (
    (By.XPATH, "//*[normalize-space()='3.7 Flash']"),
    (By.XPATH, "//*[@role='menuitem'][.//*[normalize-space()='3.7 Flash']]"),
)
MODE_SELECTORS = (
    (By.XPATH, "//*[normalize-space()='Tư duy mở rộng']"),
    (By.XPATH, "//*[@role='menuitemcheckbox'][contains(.,'Tư duy mở rộng')]"),
)
PROMPT_SELECTORS = (
    (By.CSS_SELECTOR, "div[contenteditable='true'][role='textbox']"),
    (By.CSS_SELECTOR, "rich-textarea div[contenteditable='true']"),
)
RESPONSE_SELECTORS = (
    (By.CSS_SELECTOR, "message-content"),
    (By.CSS_SELECTOR, "div[data-test-id='response-content']"),
)
```

Mỗi bước không tìm thấy element trong timeout phải ném `GeminiBrowserError` với code
cụ thể; không click theo tọa độ và không tự suy đoán model khác. Account menu chỉ dùng
email trong bộ nhớ để băm rồi xóa biến; log chỉ nhận masked hint và SHA-256.

- [ ] **Step 5: Test lỗi account, model, upload, response và URL trống**

Mỗi lỗi phải dừng trước action kế tiếp. Thêm test phiên thứ hai không lấy được profile
lock. `RecordingDriver` là fake ở đúng ranh giới Selenium; validation và orchestration
vẫn chạy code thật.

- [ ] **Step 6: Chạy test Task 3**

Run: `uv run pytest tests/unit/test_gemini_selenium.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/anime_review_mvp/gemini_selenium.py tests/unit/test_gemini_selenium.py
git commit -m "feat: control visible Gemini Chrome session"
```

---

### Task 4: Packet kiểm định bất biến cho ba phase

**Files:**
- Create: `src/anime_review_mvp/gemini_packets.py`
- Create: `tests/unit/test_gemini_packets.py`
- Modify: `src/anime_review_mvp/media.py`

**Interfaces:**
- Produces: `GeminiBrowserPacket`, `build_browser_packet(run_dir: Path, phase: str, *, beat_ids: tuple[str, ...] | None = None, runner: Runner = subprocess.run) -> GeminiBrowserPacket`.
- Consumes: source video/run state, storyboard/script, proxy/final MP4 và manifest hiện có.

- [ ] **Step 1: Viết test phase packet và hash**

```python
@pytest.mark.parametrize(
    ("phase", "expected_media"),
    (("SCRIPT", "script_evidence.mp4"), ("PROXY", "proxy_review.mp4"),
     ("FINAL", "final_candidate.mp4")),
)
def test_builds_hashed_phase_packet(tmp_path: Path, phase: str, expected_media: str) -> None:
    run = write_packet_fixture(tmp_path, phase)
    packet = build_browser_packet(run, phase, runner=fake_ffmpeg_runner)
    assert Path(packet.media_path).name == expected_media
    assert packet.phase == phase
    assert packet.packet_sha256 == sha256_packet(packet)
    assert all(Path(path).is_file() for path in packet.upload_paths)
```

- [ ] **Step 2: Chạy test RED**

Run: `uv run pytest tests/unit/test_gemini_packets.py -v`

Expected: FAIL vì packet builder chưa tồn tại.

- [ ] **Step 3: Cài đặt manifest và packet phase**

`GeminiBrowserPacket` chứa `phase`, `media_path`, `manifest_path`, `prompt_path`,
`upload_paths`, `packet_sha256`, `beat_ids`.

- `SCRIPT`: FFmpeg nối đúng source ranges của storyboard theo thứ tự, giữ audio nguồn ở
  mức mute và burn-in `beat_id | source HH:MM:SS.mmm`; kèm storyboard/script JSON.
- `PROXY`: copy proxy candidate vào packet bằng `shutil.copy2`; kèm EDL/mapping và vùng
  cấm.
- `FINAL`: copy final candidate; kèm final manifest và mapping nguồn–chương trình.

Manifest liệt kê SHA-256 từng file và chính xác beat order. Packet hash là canonical
SHA-256 của manifest. Mọi path phải nằm trong run hoặc episode hiện tại và không symlink.

- [ ] **Step 4: Test từ chối OP/ED range, symlink, thiếu beat và file đổi sau manifest**

Test `SCRIPT` phải từ chối range giao vùng loại trừ; `PROXY/FINAL` phải từ chối thiếu
mapping. `verify_packet()` phải phát hiện một byte bị đổi sau khi tạo.

- [ ] **Step 5: Chạy test Task 4**

Run: `uv run pytest tests/unit/test_gemini_packets.py tests/integration/test_media_ffmpeg.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/anime_review_mvp/gemini_packets.py src/anime_review_mvp/media.py tests/unit/test_gemini_packets.py tests/integration/test_media_ffmpeg.py
git commit -m "feat: build immutable Gemini browser packets"
```

---

### Task 5: Giao dịch operator hoàn chỉnh và parse response

**Files:**
- Modify: `src/anime_review_mvp/gemini_operator.py`
- Modify: `src/anime_review_mvp/gemini_web.py`
- Modify: `tests/unit/test_gemini_operator.py`
- Modify: `tests/unit/test_gemini_web.py`

**Interfaces:**
- Produces: `GeminiWebOperator.run(request, packet) -> OperatorReceipt`.
- Consumes: `launch_managed_chrome`, `run_gemini_session`, `OperatorLedger`, `GeminiBrowserPacket`.

- [ ] **Step 1: Viết test operator chỉ ghi ledger sau browser và schema PASS**

```python
def test_operator_commits_receipt_only_after_real_response_parses(tmp_path: Path) -> None:
    operator = operator_fixture(tmp_path, response=valid_critic_json("SCRIPT"))
    receipt = operator.run(valid_request(), valid_packet())
    assert receipt.phase == "SCRIPT"
    assert operator.ledger.verified_entry(receipt.nonce) == receipt
    assert Path(receipt.raw_response_path).read_text(encoding="utf-8") != Path(
        receipt.critic_path
    ).read_text(encoding="utf-8")
```

- [ ] **Step 2: Chạy test RED**

Run: `uv run pytest tests/unit/test_gemini_operator.py::test_operator_commits_receipt_only_after_real_response_parses -v`

Expected: FAIL vì orchestrator chưa tồn tại.

- [ ] **Step 3: Cài đặt transaction theo thứ tự bất biến**

```python
class GeminiWebOperator:
    def run(self, request: OperatorRequest, packet: GeminiBrowserPacket) -> OperatorReceipt:
        verify_packet(packet)
        launch = self._launch_browser()
        observation, raw_text = self._browser_session(launch, request, packet)
        raw_path = self._write_raw_response_envelope(
            request, observation.conversation_url, raw_text
        )
        critic_path = self._parse_and_write_critic(request.phase, raw_text)
        validate_browser_evidence(
            observation, self._policy, raw_response=raw_path, critic=critic_path
        )
        receipt = self._build_receipt(request, packet, observation, raw_path, critic_path)
        signature = self._ledger.append(receipt)
        return replace(receipt, ledger_signature=signature)
```

Raw response được lưu thành envelope JSON gồm `dom_text`, `conversation_url`,
`captured_at`, `run_id`, `phase`; critic là JSON semantic đã parse riêng nên hai artifact
không thể là cùng một file. Nếu JSON nằm trong markdown fence, parser chỉ bóc đúng một
fenced JSON block; văn bản có hai block, thiếu beat hoặc schema sai bị từ chối. Không
được tự tạo critic MATCH mặc định.

- [ ] **Step 4: Chuyển `gemini_web.py` sang xác minh operator receipt**

Xóa niềm tin vào `session.strongest_mode_confirmed` và `browser_status`. Hàm mới:

```python
def load_operator_verified_review[T](
    run_dir: Path,
    phase: str,
    review_cls: type[T],
    *,
    ledger: OperatorLedger,
) -> T:
    receipt = load_json(phase_dir / "operator_receipt.json", OperatorReceipt)
    request = load_json(phase_dir / "operator_request.json", OperatorRequest)
    verify_operator_receipt(receipt, ledger, expected_request=request)
    verify_request_dependencies(run_dir, load_json(phase_dir / "request.json", GeminiWebRequest))
    return load_json(Path(receipt.critic_path), review_cls)
```

- [ ] **Step 5: Test raw response, screenshot, artifact và packet đổi sau phiên**

Từng trường hợp phải fail trước khi critic được dùng để advance workflow.

- [ ] **Step 6: Chạy test Task 5**

Run: `uv run pytest tests/unit/test_gemini_operator.py tests/unit/test_gemini_web.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/anime_review_mvp/gemini_operator.py src/anime_review_mvp/gemini_web.py tests/unit/test_gemini_operator.py tests/unit/test_gemini_web.py
git commit -m "feat: require trusted Gemini operator transaction"
```

---

### Task 6: CLI fail-closed và loại bỏ đường manual accept

**Files:**
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `tests/unit/test_cli_antigravity.py`
- Modify: `tests/unit/test_workflow.py`
- Modify: `tests/acceptance/test_episode_pipeline.py`

**Interfaces:**
- Produces CLI: `gemini-web enroll|smoke|run --run RUN_DIR [--phase script|proxy|final]`.
- Consumes: `GeminiWebOperator`, `build_browser_packet`, `load_operator_verified_review`.

- [ ] **Step 1: Viết test parser từ chối `web-verify accept` và run gọi operator**

```python
def test_manual_web_accept_no_longer_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        cli.main(["web-verify", "accept", "--run", "run", "--phase", "script"])

def test_gemini_web_run_owns_browser_and_acceptance(tmp_path: Path, monkeypatch) -> None:
    run = write_script_gate_fixture(tmp_path)
    called = []
    monkeypatch.setattr(cli, "run_operator_phase", lambda run_dir, phase: called.append(phase))
    assert cli.main(["gemini-web", "run", "--run", str(run), "--phase", "script"]) == 0
    assert called == ["SCRIPT"]
    assert read_state(run).stage is Stage.TAO_TTS
```

- [ ] **Step 2: Chạy test RED**

Run: `uv run pytest tests/unit/test_cli_antigravity.py -v`

Expected: FAIL vì CLI cũ vẫn cho manual accept.

- [ ] **Step 3: Thay CLI và map lỗi browser sang trạng thái dừng**

`enroll` chỉ ghi account hash/hint sau khi user nhập email trên stdin. `smoke` mở Chrome,
gửi prompt cố định `Trả lời đúng chuỗi GEMINI_WEB_OPERATOR_OK` và yêu cầu chat URL thật.
`run` kiểm tra stage, build packet, issue nonce, chạy operator, load critic và thực thi
semantic repair/advance hiện có trong cùng một lệnh.

Thêm `HumanCode` hoặc mã string khóa:

```python
BROWSER_HUMAN_CODES = {
    "LOGIN_REQUIRED": "CAN_DANG_NHAP_GEMINI_ULTRA",
    "ACCOUNT_MISMATCH": "SAI_TAI_KHOAN_GEMINI",
    "MODEL_NOT_FOUND": "KHONG_THAY_MODEL_3_7_FLASH",
    "UPLOAD_FAILED": "GEMINI_UPLOAD_THAT_BAI",
    "INVALID_RESPONSE": "GEMINI_RESPONSE_KHONG_HOP_LE",
    "INVALID_EVIDENCE": "BANG_CHUNG_BROWSER_KHONG_HOP_LE",
}
```

Mọi mã gọi `mark_human_required()` và ghi `next_action.json`; không gọi render tiếp.

- [ ] **Step 4: Acceptance test ba phase và lỗi không advance**

Fixture operator tạo signed ledger thật bằng key test. Pipeline phải qua `SCRIPT`,
`PROXY`, `FINAL` chỉ khi receipt hợp lệ; một ảnh đen tại `FINAL` phải giữ run ngoài
`KIEM_DINH_ENGINE`.

- [ ] **Step 5: Chạy test Task 6**

Run: `uv run pytest tests/unit/test_cli_antigravity.py tests/unit/test_workflow.py tests/acceptance/test_episode_pipeline.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/anime_review_mvp/cli.py src/anime_review_mvp/workflow.py tests/unit/test_cli_antigravity.py tests/unit/test_workflow.py tests/acceptance/test_episode_pipeline.py
git commit -m "feat: make Gemini browser operation fail closed"
```

---

### Task 7: Revision cache isolation và BLACK TORCH clean revision

**Files:**
- Modify: `src/anime_review_mvp/tts.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/workspace.py`
- Modify: `tests/unit/test_tts.py`
- Modify: `tests/unit/test_workspace.py`

**Interfaces:**
- Produces: `TtsCacheIdentity`, revision-scoped cache key và `prepare_clean_revision()`.
- Consumes: run ID, source SHA-256, cue text, voice profile và policy version.

- [ ] **Step 1: Viết test revision mới buộc miss toàn bộ**

```python
def test_new_revision_invalidates_every_atomic_tts_entry(tmp_path: Path) -> None:
    first = synthesize_atomic_beats(
        storyboard(), tmp_path / "out-1", tmp_path / "cache",
        revision_id="rev-a", source_sha256="1" * 64,
        provider=provider(), converter=converter,
    )
    second = synthesize_atomic_beats(
        storyboard(), tmp_path / "out-2", tmp_path / "cache",
        revision_id="rev-b", source_sha256="1" * 64,
        provider=provider(), converter=converter,
    )
    assert first.cache_stats.misses == len(storyboard().beats)
    assert second.cache_stats.misses == len(storyboard().beats)
    assert second.cache_stats.hits == 0
```

- [ ] **Step 2: Chạy test RED**

Run: `uv run pytest tests/unit/test_tts.py::test_new_revision_invalidates_every_atomic_tts_entry -v`

Expected: FAIL vì API chưa nhận revision/source hash.

- [ ] **Step 3: Mở rộng cache identity**

```python
def _atomic_tts_cache_key(
    text: str,
    profile: VoiceProfile,
    policy_version: str,
    revision_id: str,
    source_sha256: str,
) -> str:
    normalized = normalize_speech_text(text)
    raw = "\0".join((
        normalized, profile.provider, profile.voice_id, policy_version,
        revision_id, source_sha256,
    ))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

CLI truyền `run_dir.name` làm revision ID và source SHA từ truth/source ref. Trong cùng
revision, cue không đổi vẫn hit; đổi một cue chỉ miss đúng beat đó.

- [ ] **Step 4: Cài đặt clean revision không xóa bản cũ**

`prepare_clean_revision()` tạo run mới, không copy TTS/EDL/critic/proxy/final cũ và giữ
`Thanh_pham/review_anime.mp4` hiện tại nguyên vẹn. Candidate mới chỉ publish sau final
operator PASS và engine audit PASS.

- [ ] **Step 5: Chạy test Task 7**

Run: `uv run pytest tests/unit/test_tts.py tests/unit/test_workspace.py tests/unit/test_cli_antigravity.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/anime_review_mvp/tts.py src/anime_review_mvp/cli.py src/anime_review_mvp/workspace.py tests/unit/test_tts.py tests/unit/test_workspace.py tests/unit/test_cli_antigravity.py
git commit -m "fix: isolate TTS and render caches by revision"
```

---

### Task 8: Khóa chỉ dẫn Antigravity theo operator thật

**Files:**
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Modify: `PROMPT_MOT_LAN_CHAY.md`
- Modify: `src/anime_review_mvp/antigravity.py`
- Modify: `tests/unit/test_antigravity_contract.py`
- Modify: `tests/unit/test_cli_antigravity.py`

**Interfaces:**
- Produces prompt một lần chạy chỉ dùng `gemini-web run`.
- Consumes CLI Task 6 và browser failure codes.

- [ ] **Step 1: Viết contract test cấm các hành vi cũ**

```python
def test_antigravity_policy_forbids_manual_browser_artifacts() -> None:
    policy = Path("Bo_nao_Antigravity/GEMINI.md").read_text(encoding="utf-8")
    assert "gemini-web run" in policy
    assert "web-verify accept" not in policy
    assert "không tự tạo receipt" in policy.casefold()
    assert "không dùng ffmpeg tạo ảnh phiên" in policy.casefold()
    assert "3.7 Flash" in policy
    assert "Tư duy mở rộng" in policy
```

- [ ] **Step 2: Chạy test RED**

Run: `uv run pytest tests/unit/test_antigravity_contract.py -v`

Expected: FAIL vì chỉ dẫn cũ vẫn còn đường prepare/accept thủ công.

- [ ] **Step 3: Viết lại chỉ dẫn ngắn và bất biến**

Antigravity phải đọc `next_action.json` sau mỗi lệnh; tại ba cổng chỉ được chạy:

```text
uv run python run_episode.py gemini-web run --run "$runDir" --phase script
uv run python run_episode.py gemini-web run --run "$runDir" --phase proxy
uv run python run_episode.py gemini-web run --run "$runDir" --phase final
```

Cấm tự ghi `response.txt`, `critic_*.json`, `operator_receipt.json`, screenshot, ledger;
cấm dùng FFmpeg/ImageMagick tạo ảnh phiên; cấm khai model/account/READY bằng text. Khi CLI
dừng vì login/CAPTCHA, Antigravity báo đúng `next_action` và chờ người dùng.

- [ ] **Step 4: Chạy contract và prompt tests**

Run: `uv run pytest tests/unit/test_antigravity_contract.py tests/unit/test_cli_antigravity.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add Bo_nao_Antigravity/GEMINI.md PROMPT_MOT_LAN_CHAY.md src/anime_review_mvp/antigravity.py tests/unit/test_antigravity_contract.py tests/unit/test_cli_antigravity.py
git commit -m "docs: restrict Antigravity to trusted web operator"
```

---

### Task 9: Verification toàn bộ và smoke test Chrome thật

**Files:**
- Create: `tests/manual/gemini_web_smoke.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-29-gemini-web-operator-design.md` only if an observed Gemini DOM label differs from the approved exact wording.

**Interfaces:**
- Consumes toàn bộ operator, CLI, profile binding và Chrome đã cài.
- Produces smoke report trong exact run diagnostics và hướng dẫn đăng nhập một lần.

- [ ] **Step 1: Tạo manual smoke entrypoint dùng code production**

```python
def main() -> int:
    run_dir = Path(sys.argv[1]).resolve(strict=True)
    return cli.main(["gemini-web", "smoke", "--run", str(run_dir)])

if __name__ == "__main__":
    raise SystemExit(main())
```

Script không chứa selector hoặc logic browser riêng; nó chỉ gọi production CLI.

- [ ] **Step 2: Chạy toàn bộ kiểm thử tự động**

Run: `uv run pytest -q`

Expected: tất cả test PASS, không warning ngoài warning dependency đã ghi nhận.

Run: `uv run ruff check .`

Expected: `All checks passed!`

- [ ] **Step 3: Kiểm tra dependency và policy hash**

Run: `uv sync --locked`

Expected: exit 0.

Set once in PowerShell:

```powershell
$operatorSmokeRun = 'D:\FINAL REVIEW ANIME\Tam_dang_xu_ly\a58b66d2cdb041e4bb94a63529bb6047'
```

Run: `uv run python run_episode.py prompt --run $operatorSmokeRun`

Expected: prompt tạo được và policy SHA-256 khớp code hiện tại.

- [ ] **Step 4: Chạy smoke Chrome hữu hình**

Run: `uv run python tests/manual/gemini_web_smoke.py $operatorSmokeRun`

Expected trên màn hình người dùng:

1. Chrome profile chuyên dụng mở hữu hình;
2. nếu chưa đăng nhập, CLI dừng `CAN_DANG_NHAP_GEMINI_ULTRA` để người dùng đăng nhập;
3. chạy lại sau đăng nhập chọn đúng `3.7 Flash` và `Tư duy mở rộng`;
4. chat mới gửi prompt và Gemini trả `GEMINI_WEB_OPERATOR_OK`;
5. URL chat khác `/app` và chat xuất hiện trong lịch sử;
6. screenshot thật, raw response, signed ledger và receipt được tạo;
7. không có file nào do Antigravity tự ghi.

- [ ] **Step 5: Chạy packet nhỏ BLACK TORCH, chưa render toàn tập**

Dùng run chẩn đoán hiện có chỉ làm nguồn packet, gọi
`build_browser_packet(run, "SCRIPT", beat_ids=("beat-001", "beat-002", "beat-003"))`
và chạy operator với request smoke riêng. Xác nhận Gemini nhận video, nhìn thấy burn-in
beat/timestamp và trả JSON đủ ba beat. Run này không được advance hoặc publish. Nếu
upload/DOM lỗi, sửa operator và lặp smoke; không chạy tiếp TTS/render. Revision BLACK
TORCH sạch chỉ được tạo sau khi packet smoke PASS.

- [ ] **Step 6: Ghi báo cáo nghiệm thu và commit**

README ghi đúng ba lệnh người dùng cần: enroll một lần, smoke, prompt gửi Antigravity.
Báo cáo smoke chỉ lưu masked account, model/mode, URL chat, hashes và ảnh phiên; không lưu
email đầy đủ hoặc cookie.

```bash
git add tests/manual/gemini_web_smoke.py README.md
git commit -m "test: verify real Gemini Ultra browser session"
```

- [ ] **Step 7: Review cuối trước khi cho phép chạy lại tập**

Run: `git status --short --branch`

Expected: chỉ còn các runtime directory có sẵn của người dùng; không có source/test chưa
commit. Chỉ khi toàn bộ test, Ruff, smoke Chrome và packet nhỏ PASS mới sinh prompt để
Antigravity chạy revision BLACK TORCH hoàn chỉnh.
