# Antigravity-First Atomic Beat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển pipeline từ Codex biên tập từng tập sang một lần chạy Antigravity tự tạo video bằng atomic beat, cache gia tăng và cổng engine không tin cờ PASS của agent.

**Architecture:** Giữ engine Python/FFmpeg hiện có nhưng thay `NarrationSpanDocument(owner="CODEX")` trong đường chạy chính bằng `AtomicStoryboard(owner="ANTIGRAVITY")`. Antigravity tạo và phản biện artifact theo từng beat; engine kiểm tra timestamp/evidence/hash, cache TTS theo nội dung, dựng proxy trước và chỉ xuất bản video cuối khi audit máy móc đạt.

**Tech Stack:** Python 3.12, dataclasses, JSON strict loader hiện có, pytest, Ruff, FFmpeg/ffprobe, local TikTok/CapCut TTS `BV074_streaming`.

**Spec:** `docs/superpowers/specs/2026-08-28-antigravity-first-atomic-beat-design.md`

## Global Constraints

- Một run chỉ xử lý đúng một tập dub tiếng Anh.
- Thành phẩm dài 420–720 giây và chỉ có một video stream cùng một audio stream TTS tiếng Việt.
- Giọng TTS bắt buộc là `BV074_streaming`; không dùng audio nguồn, BGM, speed, freeze hoặc loop.
- Antigravity được ghi artifact của tập/run và gọi CLI, nhưng không được sửa `Bo_nao_Antigravity`, `src`, `tests`, `docs`, cấu hình hoặc Git.
- Codex không biên tập, tạo TTS hoặc render từng tập trong đường chạy bình thường.
- Coverage trực tiếp tối thiểu 0.90; drift audio/video và chênh source/TTS tối đa 80 ms.
- `ACTION`/`REACTION` có dung sai action-window 500 ms; `CONTEXT` có dung sai 1.000 ms.
- Không thêm MCP, repo, UI, caption, BGM, batch, cloud TTS hoặc WhisperX trong kế hoạch này.
- Mọi thay đổi hành vi phải theo Red–Green–Refactor; không sửa dữ liệu thật trong `Kho_Anime` khi chạy unit/integration test.

---

## File Structure

- `src/anime_review_mvp/models.py` — dataclass JSON cho atomic beat, critic review, cache và run metrics.
- `src/anime_review_mvp/atomic.py` — load/validate storyboard và critic artifact, tính hash nội dung beat.
- `src/anime_review_mvp/workflow.py` — stage Antigravity-first và repair theo danh sách beat.
- `src/anime_review_mvp/antigravity.py` — job contract, output bắt buộc, policy hash và quyền ghi.
- `src/anime_review_mvp/tts.py` — TTS cache theo beat, nối WAV từ cache hit/miss.
- `src/anime_review_mvp/edl.py` — sinh EDL nguyên tử từ source range và WAV thật.
- `src/anime_review_mvp/audit.py` — coverage từ evidence/finding, cổng kỹ thuật và hash policy.
- `src/anime_review_mvp/cli.py` — nối stage storyboard → critic → TTS → fit → proxy → critic video → final.
- `src/anime_review_mvp/workspace.py` — thư mục cache theo tập và dọn run sau hoàn thành.
- `Bo_nao_Antigravity/GEMINI.md` — quyền hạn và vòng lặp Antigravity mới.
- `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md` — một prompt tự chạy đến MP4 hoặc báo chặn.
- `README.md` — hướng dẫn vận hành không có bước Codex biên tập.
- `tests/unit/test_atomic.py`, `test_workflow.py`, `test_antigravity_contract.py`, `test_tts.py`, `test_edl.py`, `test_audit.py`, `test_cli_antigravity.py` — kiểm thử từng ranh giới.
- `tests/acceptance/test_episode_pipeline.py` — fixture end-to-end không cần dịch vụ mạng.

---

### Task 1: Atomic storyboard contract

**Files:**
- Modify: `src/anime_review_mvp/models.py`
- Create: `src/anime_review_mvp/atomic.py`
- Create: `tests/unit/test_atomic.py`

**Interfaces:**
- Consumes: `TruthDocument`, `SourceRef`, `ShotDocument`, JSON loader hiện có.
- Produces: `AtomicBeat`, `AtomicStoryboard`, `CriticBeatReview`, `CriticReviewDocument`, `load_atomic_storyboard(path, truth, shots, source_duration_ms)`, `load_critic_review(path, storyboard, phase)`, `beat_cache_key(beat, voice_id, policy_version)`.

- [ ] **Step 1: Viết test thất bại cho một beat hợp lệ và các lỗi nguyên tử**

```python
def test_atomic_storyboard_rejects_multi_action_and_bad_action_window(tmp_path: Path) -> None:
    payload = atomic_payload()
    payload["beats"][0]["visual_fact"] = "Jiro chạy vào sân rồi ông nội đánh cậu."
    payload["beats"][0]["action_window_start_ms"] = 900
    with pytest.raises(MvpError, match="action window|one primary action"):
        load_atomic_storyboard(write_json(tmp_path / "atomic.json", payload), truth(), shots(), 10_000)


def test_atomic_storyboard_accepts_multiple_shots_for_one_action(tmp_path: Path) -> None:
    document = load_atomic_storyboard(
        write_json(tmp_path / "atomic.json", atomic_payload()), truth(), shots(), 10_000
    )
    assert document.owner == "ANTIGRAVITY"
    assert document.beats[0].source_ranges[0].shot_ids == ("shot-001", "shot-002")
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `uv run pytest tests/unit/test_atomic.py -v`

Expected: FAIL vì model/module atomic chưa tồn tại.

- [ ] **Step 3: Thêm model strict tối thiểu**

```python
@dataclass(frozen=True, slots=True)
class AtomicBeat:
    beat_id: str
    scene_id: str
    event_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    source_ranges: tuple[SpanSourceRange, ...]
    visual_fact: str
    characters_visible: tuple[str, ...]
    characters_spoken_about: tuple[str, ...]
    sync_mode: str
    action_window_start_ms: int | None
    action_window_end_ms: int | None
    narration_text: str
    frame_evidence: tuple[str, ...]
    estimated_tts_ms: int
    actual_tts_ms: int | None
    tts_cache_key: str
    status: str
    finding_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AtomicStoryboard:
    owner: str
    policy_version: str
    beats: tuple[AtomicBeat, ...]
    claims: tuple[Claim, ...]
```

`load_atomic_storyboard` phải yêu cầu owner `ANTIGRAVITY`, ID duy nhất, đúng một câu/ý, một primary action, status hợp lệ, event/claim/shot tồn tại, source range nằm trong source và không giao vùng `EXCLUDE`. `ACTION`/`REACTION` bắt buộc action window nằm trong source range; `CONTEXT` bắt buộc hai trường action window là `null`.

- [ ] **Step 4: Thêm critic contract không có trường PASS**

`CriticReviewDocument` chỉ chứa `phase`, `producer_context_id`, `critic_context_id`, `beat_reviews`; hai context ID phải khác nhau. Mỗi review chứa `beat_id`, `finding_codes`, `evidence_refs`, `note`. JSON có `passed` phải bị strict loader từ chối.

- [ ] **Step 5: Chạy test atomic và toàn bộ unit test**

Run: `uv run pytest tests/unit/test_atomic.py tests/unit/test_models.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/anime_review_mvp/models.py src/anime_review_mvp/atomic.py tests/unit/test_atomic.py tests/unit/test_models.py
git commit -m "feat: add atomic storyboard contract"
```

### Task 2: Workflow Antigravity-first và repair theo beat

**Files:**
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `tests/unit/test_workflow.py`

**Interfaces:**
- Consumes: `Stage`, persisted `run_state.json`.
- Produces: stage mới, `record_beat_repair(run_dir, phase, beat_ids, codes)`, `StageMetrics` trong state.

- [ ] **Step 1: Viết test thất bại cho đường stage mới**

```python
def test_antigravity_workflow_has_no_codex_editor_stage(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run")
    path = [Stage.CHUAN_BI, Stage.QUAN_SAT, Stage.LAP_STORYBOARD, Stage.VIET_LOI,
            Stage.PHAN_BIEN_KICH_BAN, Stage.TAO_TTS, Stage.CAN_TTS,
            Stage.DUNG_PROXY, Stage.PHAN_BIEN_VIDEO, Stage.DUNG_VIDEO_CUOI,
            Stage.KIEM_DINH_ENGINE, Stage.HOAN_THANH]
    assert Stage.CODEX_BIEN_TAP not in path
    assert state.stage is path[0]


def test_repair_records_only_failed_beats(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run", stage=Stage.PHAN_BIEN_VIDEO)
    repaired = record_beat_repair(state.run_dir, "VIDEO", ("beat-003",), ("VOICE_AHEAD",))
    assert repaired.stage is Stage.SUA_BEAT
    assert repaired.repair_history[-1].beat_ids == ("beat-003",)
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `uv run pytest tests/unit/test_workflow.py -v`

Expected: FAIL vì stage và repair API mới chưa tồn tại.

- [ ] **Step 3: Thay state machine và giữ giới hạn ba vòng**

Mỗi `RepairRecord` ghi `phase`, `beat_ids`, `codes`. Vòng thứ ba còn lỗi chuyển
`CAN_CON_NGUOI_XU_LY`; hai vòng đầu chuyển `SUA_BEAT`, sau khi sửa quay về
`PHAN_BIEN_KICH_BAN` hoặc `TAO_TTS` tùy code. Không giữ `CODEX_BIEN_TAP` trong
`_NEXT_STAGE` của đường chạy mới.

- [ ] **Step 4: Thêm metrics stage có thời gian/cache counters**

```python
@dataclass(frozen=True, slots=True)
class StageMetric:
    stage: str
    elapsed_ms: int
    cache_hits: int
    cache_misses: int
    changed_beat_ids: tuple[str, ...]
```

`record_stage_metric` append dữ liệu đo được; không nhận số âm.

- [ ] **Step 5: Chạy test workflow**

Run: `uv run pytest tests/unit/test_workflow.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/anime_review_mvp/workflow.py tests/unit/test_workflow.py
git commit -m "feat: move workflow ownership to Antigravity"
```

### Task 3: Job permissions, policy hash và cache paths

**Files:**
- Modify: `src/anime_review_mvp/antigravity.py`
- Modify: `src/anime_review_mvp/workspace.py`
- Modify: `tests/unit/test_antigravity_contract.py`
- Modify: `tests/unit/test_workspace.py`

**Interfaces:**
- Consumes: `JobPaths`, brain/config files.
- Produces: `OperatorJob.policy_sha256`, output paths mới, `JobPaths.cache_dir`, `verify_policy_hash(job, root)`.

- [ ] **Step 1: Viết test thất bại cho quyền Antigravity mới**

```python
def test_operator_job_allows_episode_outputs_but_locks_brain_and_code(tmp_path: Path) -> None:
    payload = prepared_job_payload(tmp_path)
    outputs = payload["required_outputs"]
    assert outputs["storyboard"].endswith("atomic_storyboard.json")
    assert outputs["critic_script"].endswith("critic_script.json")
    assert outputs["critic_video"].endswith("critic_video.json")
    assert payload["policy_sha256"]
    assert any(path.endswith("Bo_nao_Antigravity") for path in payload["write_policy"]["read_only_roots"])
    assert any(path.endswith("src") for path in payload["write_policy"]["read_only_roots"])
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `uv run pytest tests/unit/test_antigravity_contract.py tests/unit/test_workspace.py -v`

Expected: FAIL vì job cũ chỉ cho bản nháp và chưa có policy hash/cache dir.

- [ ] **Step 3: Đổi job contract**

`required_outputs` trỏ đến truth, scene, storyboard, critic script và critic video.
Cho phép Antigravity ghi episode artifact/report và run temp thông qua CLI; vẫn khóa
source, brain, `src`, `tests`, `docs`, `.git` và config. Policy hash là SHA-256 của
`GEMINI.md`, prompt, `pyproject.toml` và danh sách file validator được sắp thứ tự.

- [ ] **Step 4: Thêm cache dir theo tập**

`JobPaths.cache_dir` là `<Tap_XXX>/_Cache`; tạo các thư mục `source`, `tts`, `clips`,
`qa`. `cleanup_completed_run` chỉ xóa proxy/frame tạm trong đúng run đã resolve và
đã xác nhận nằm dưới `Tam_dang_xu_ly`; không xóa cache hoặc báo cáo.

- [ ] **Step 5: Chạy test contract/workspace**

Run: `uv run pytest tests/unit/test_antigravity_contract.py tests/unit/test_workspace.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/anime_review_mvp/antigravity.py src/anime_review_mvp/workspace.py tests/unit/test_antigravity_contract.py tests/unit/test_workspace.py
git commit -m "feat: grant scoped episode execution to Antigravity"
```

### Task 4: TTS cache gia tăng theo beat

**Files:**
- Modify: `src/anime_review_mvp/tts.py`
- Modify: `tests/unit/test_tts.py`

**Interfaces:**
- Consumes: `AtomicStoryboard`, TTS cache directory.
- Produces: `synthesize_atomic_beats(storyboard, output_dir, cache_dir, provider, converter) -> AtomicTtsManifest` và `TtsCacheStats`.

- [ ] **Step 1: Viết test RED chứng minh beat không đổi không gọi provider lần hai**

```python
def test_atomic_tts_reuses_unchanged_beat(tmp_path: Path) -> None:
    provider = CountingProvider()
    first = synthesize_atomic_beats(storyboard("Cậu lao vào sân."), tmp_path / "out", tmp_path / "cache", provider=provider, converter=fake_converter)
    second = synthesize_atomic_beats(storyboard("Cậu lao vào sân."), tmp_path / "out2", tmp_path / "cache", provider=provider, converter=fake_converter)
    assert provider.calls == 1
    assert first.spans[0].cache_key == second.spans[0].cache_key
    assert second.cache_stats.hits == 1
```

- [ ] **Step 2: Viết test RED cho invalidation đúng một beat**

Hai beat chạy lần đầu tạo hai call; đổi text beat thứ hai rồi chạy lại phải có tổng ba
call, một hit và một miss. Voice ID hoặc policy version đổi phải tạo cache miss.

- [ ] **Step 3: Chạy test và xác nhận RED**

Run: `uv run pytest tests/unit/test_tts.py -v`

Expected: FAIL vì `synthesize_atomic_beats` và cache manifest chưa tồn tại.

- [ ] **Step 4: Cài đặt cache bằng SHA-256 và atomic replace**

Cache key lấy từ normalized narration text, provider, voice ID, audio policy và policy
version. Mỗi entry chứa MP3, WAV và metadata duration; chỉ coi là hit khi đủ ba file,
hash khớp và WAV qua `_wav_duration_ms`. Ghi file tạm trong cache entry rồi
`os.replace`; không tin duration cũ nếu WAV hỏng.

- [ ] **Step 5: Nối narration từ WAV cache theo thứ tự beat**

Copy/hardlink WAV beat vào `TTS`; tạo `narration.wav` từ danh sách beat hiện hành và
ghi `atomic_tts_manifest.json` có hit/miss cùng cache key từng beat.

- [ ] **Step 6: Chạy test TTS**

Run: `uv run pytest tests/unit/test_tts.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/anime_review_mvp/tts.py src/anime_review_mvp/models.py tests/unit/test_tts.py
git commit -m "feat: cache TTS by atomic beat"
```

### Task 5: Atomic EDL, action window và coverage xác định

**Files:**
- Modify: `src/anime_review_mvp/edl.py`
- Modify: `src/anime_review_mvp/audit.py`
- Modify: `tests/unit/test_edl.py`
- Modify: `tests/unit/test_audit.py`

**Interfaces:**
- Consumes: `AtomicStoryboard`, `AtomicTtsManifest`, source/program evidence, critic review.
- Produces: `build_atomic_edl(storyboard, tts, tolerance_ms=80, minimum_segment_ms=500)`, `build_atomic_engine_audit(...)`.

- [ ] **Step 1: Viết EDL test RED**

```python
def test_atomic_edl_rejects_action_window_outside_selected_footage() -> None:
    board = atomic_storyboard(action_window=(4_100, 4_500), source_range=(1_000, 4_000))
    with pytest.raises(MvpError, match="action window"):
        build_atomic_edl(board, atomic_tts(3_000))


def test_atomic_edl_accepts_many_shots_for_one_beat() -> None:
    edl = build_atomic_edl(atomic_storyboard(source_range=(1_000, 4_000), shot_ids=("s1", "s2")), atomic_tts(3_000))
    assert {shot for segment in edl.segments for shot in segment.shot_ids} == {"s1", "s2"}
```

- [ ] **Step 2: Viết audit test RED cho coverage không dùng boolean agent**

```python
def test_atomic_audit_counts_only_evidenced_beats_without_blocking_findings() -> None:
    report = build_atomic_engine_audit(board_two_beats(), tts_two_beats(), critic_with_error_on_second(), evidence(), render_result())
    assert report.coverage_ratio == "0.5"
    assert report.passed is False
    assert "DIRECT_EVIDENCE_BELOW_90" in {finding.code for finding in report.findings}
```

- [ ] **Step 3: Chạy test và xác nhận RED**

Run: `uv run pytest tests/unit/test_edl.py tests/unit/test_audit.py -v`

Expected: FAIL vì API atomic chưa tồn tại.

- [ ] **Step 4: Cài atomic EDL**

Mỗi beat phải có tổng source duration khớp WAV trong 80 ms, range ít nhất 500 ms nếu
không có short-action exception, không reuse source overlap và program timing liên
tục. Action window phải nằm trong footage; validator tính lead/lag từ program mapping
và chặn vượt 500/1.000 ms theo sync mode.

- [ ] **Step 5: Cài engine audit 0.90**

Coverage numerator là tổng actual TTS của beat đủ evidence và không có finding chặn;
denominator là tổng actual TTS. Audit tự kiểm tra policy hash, duration 420–720 giây,
stream layout 1/1, drift 80 ms, mọi beat `LOCKED`, audio source bị loại và critic
context khác producer. Input review không có trường `passed`.

- [ ] **Step 6: Chạy test EDL/audit**

Run: `uv run pytest tests/unit/test_edl.py tests/unit/test_audit.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/anime_review_mvp/edl.py src/anime_review_mvp/audit.py tests/unit/test_edl.py tests/unit/test_audit.py
git commit -m "feat: enforce atomic scene voice evidence"
```

### Task 6: CLI proxy-first và xuất bản cuối một lần

**Files:**
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/render.py`
- Create: `tests/unit/test_cli_antigravity.py`
- Modify: `tests/integration/test_render_ffmpeg.py`

**Interfaces:**
- Consumes: atomic loaders, TTS cache, EDL/audit APIs.
- Produces: CLI `validate --artifact storyboard|critic-script|critic-video|edl`, `tts`, `render --quality proxy|final`, `audit --phase engine`.

- [ ] **Step 1: Viết test RED cho một đường chạy không dừng chờ Codex**

```python
def test_cli_advances_from_storyboard_to_antigravity_tts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run, episode = prepared_atomic_run(tmp_path, Stage.LAP_STORYBOARD)
    write_atomic_storyboard(episode)
    assert main(["validate", "--run", str(run), "--artifact", "storyboard"]) == 0
    assert read_state(run).stage is Stage.VIET_LOI
    assert "Codex" not in json.loads((run / "next_action.json").read_text(encoding="utf-8"))["instruction"]
```

- [ ] **Step 2: Viết test RED cho proxy không ghi đè thành phẩm**

`render --quality proxy` phải ghi `<run>/proxy/review_proxy.mp4`; `render --quality
final` chỉ hợp lệ sau critic-video sạch và ghi candidate trong run. Chỉ audit engine
đạt mới gọi `publish_candidate`.

- [ ] **Step 3: Chạy test và xác nhận RED**

Run: `uv run pytest tests/unit/test_cli_antigravity.py -v`

Expected: FAIL vì parser/stage cũ còn `lock`, `CODEX_BIEN_TAP` và `--codex-review`.

- [ ] **Step 4: Nối CLI mới**

Xóa `lock` khỏi đường chạy tài liệu và parser chính. `validate storyboard` trích source
evidence theo beat; `critic-script` ghi finding và quyết định repair; `tts` dùng cache;
`validate edl` chuyển dựng proxy; `critic-video` quyết định repair hoặc final render;
`audit engine` tự tính báo cáo, publish và dọn file tạm đúng run.

- [ ] **Step 5: Tách proxy render khỏi final render**

Proxy dùng H.264 360p preset nhanh và TTS-only. Final giữ độ phân giải/fps nguồn, map
chính xác một video + narration WAV, `-map_metadata -1`, không map audio nguồn. Cả hai
đều dùng cùng atomic EDL nên proxy/final không đổi timeline.

- [ ] **Step 6: Chạy CLI và FFmpeg integration test**

Run: `uv run pytest tests/unit/test_cli_antigravity.py tests/integration/test_render_ffmpeg.py -v`

Expected: PASS; integration test skip rõ ràng nếu FFmpeg không khả dụng.

- [ ] **Step 7: Commit**

```bash
git add src/anime_review_mvp/cli.py src/anime_review_mvp/render.py tests/unit/test_cli_antigravity.py tests/integration/test_render_ffmpeg.py
git commit -m "feat: add Antigravity proxy-first episode runner"
```

### Task 7: Bộ kiểm tra văn phong toàn tập

**Files:**
- Modify: `src/anime_review_mvp/validation.py`
- Modify: `tests/unit/test_validation.py`

**Interfaces:**
- Consumes: `AtomicStoryboard`.
- Produces: `atomic_style_findings(storyboard) -> tuple[AuditFinding, ...]`.

- [ ] **Step 1: Viết test RED cho văn lặp công thức**

```python
def test_atomic_style_rejects_repeated_openings_across_episode() -> None:
    board = storyboard_with_texts(
        "Lúc này Jiro lao vào sân.",
        "Lúc này ông nội quay lại.",
        "Lúc này con quái xuất hiện.",
    )
    assert "REPEATED_OPENING" in {item.code for item in atomic_style_findings(board)}
```

Thêm test cho n-gram lặp, ba câu liên tiếp cùng khung, từ nối dày, trên hai mệnh đề
chính và joke chứa claim không có trong visual fact/event.

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `uv run pytest tests/unit/test_validation.py -v`

Expected: FAIL vì validator cũ chỉ xét từng cue.

- [ ] **Step 3: Cài validator toàn tập tối giản**

Chuẩn hóa lowercase/NFC, lấy 2–4 từ mở đầu, word n-gram và mẫu dấu câu; phát finding
theo beat nhưng tính tần suất trên cả tập. Danh sách từ nối/mẫu sáo rỗng nằm trong một
constant rõ ràng. Không tạo “điểm hay” giả và không bắt buộc chèn joke.

- [ ] **Step 4: Chạy test validation**

Run: `uv run pytest tests/unit/test_validation.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anime_review_mvp/validation.py tests/unit/test_validation.py
git commit -m "feat: detect formulaic episode narration"
```

### Task 8: Khóa bộ não và prompt một lần chạy

**Files:**
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Modify: `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md`
- Modify: `README.md`
- Modify: `tests/unit/test_antigravity_contract.py`

**Interfaces:**
- Consumes: CLI/stage/artifact đã hoàn thành.
- Produces: prompt duy nhất để Antigravity tự chạy đến MP4 hoặc báo `BRAIN_CHANGE_REQUESTED`.

- [ ] **Step 1: Viết test RED cho nội dung brain mới**

```python
def test_brain_assigns_video_execution_to_antigravity_and_locks_architecture() -> None:
    brain = Path("Bo_nao_Antigravity/GEMINI.md").read_text(encoding="utf-8")
    prompt = Path("Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md").read_text(encoding="utf-8")
    for text in (brain, prompt):
        assert "atomic_storyboard.json" in text
        assert "DUNG_PROXY" in text
        assert "BV074_streaming" in text
        assert "BRAIN_CHANGE_REQUESTED" in text
        assert "CODEX_BIEN_TAP" not in text
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `uv run pytest tests/unit/test_antigravity_contract.py -v`

Expected: FAIL vì brain hiện yêu cầu dừng và giao Codex.

- [ ] **Step 3: Viết lại GEMINI.md theo stage thật**

Nêu rõ producer/critic context phải tách, mỗi beat một hành động, action window/evidence,
quy tắc sửa tối đa ba vòng, cache chỉ invalidated theo beat, proxy trước final, chỉ TTS
Việt, không sửa brain/code/Git và phải đọc `next_action.json` sau mỗi CLI command.

- [ ] **Step 4: Viết prompt một lần chạy và README**

Prompt chỉ yêu cầu đường dẫn job, tự tiếp tục theo `next_action.json` đến
`HOAN_THANH`/`CAN_CON_NGUOI_XU_LY`, sau đó báo đường dẫn MP4, tổng thời gian, cache
hit/miss, beat đã sửa và finding còn lại. README bỏ toàn bộ hướng dẫn Codex khóa span.

- [ ] **Step 5: Chạy test contract và tìm chỉ dẫn cũ**

Run: `uv run pytest tests/unit/test_antigravity_contract.py -v`

Run: `rg -n "CODEX_BIEN_TAP|Codex.*(TTS|render|khóa câu|biên tập)|codex_semantic_review" Bo_nao_Antigravity README.md`

Expected: pytest PASS; `rg` không trả về chỉ dẫn vận hành cũ.

- [ ] **Step 6: Commit**

```bash
git add Bo_nao_Antigravity/GEMINI.md Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md README.md tests/unit/test_antigravity_contract.py
git commit -m "docs: make Antigravity the episode operator"
```

### Task 9: Acceptance, regression tự động và bàn giao prompt

**Files:**
- Modify: `tests/acceptance/test_episode_pipeline.py`
- Modify: `tests/fixtures/operator_artifacts/su_that_tap_phim.json`
- Modify: `tests/fixtures/operator_artifacts/scene_packets.json`
- Create: `tests/fixtures/operator_artifacts/atomic_storyboard.json`
- Create: `tests/fixtures/operator_artifacts/critic_script.json`
- Create: `tests/fixtures/operator_artifacts/critic_video.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: toàn bộ pipeline mới với provider/render fake xác định.
- Produces: acceptance test một tập từ start đến publish, prompt sẵn để người dùng gửi Antigravity.

- [ ] **Step 1: Viết acceptance test RED**

```python
def test_one_antigravity_run_reaches_final_without_codex_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run, episode = execute_fixture_pipeline(tmp_path, monkeypatch)
    assert read_state(run).stage is Stage.HOAN_THANH
    assert (episode / "Thanh_pham" / "review_anime.mp4").is_file()
    assert not (episode / "Kich_ban" / "khoa_cau_canh.json").exists()
    assert not (episode / "Bao_cao_Codex").exists()
    assert json.loads((episode / "Bao_cao" / "kiem_dinh_engine.json").read_text(encoding="utf-8"))["passed"] is True
```

- [ ] **Step 2: Chạy acceptance test và xác nhận RED**

Run: `uv run pytest tests/acceptance/test_episode_pipeline.py -v`

Expected: FAIL vì fixture/flow cũ dừng ở Codex.

- [ ] **Step 3: Cập nhật fixture và fake boundary**

Fake provider tạo WAV 24 kHz mono có duration đúng source range; fake renderer tạo
`RenderResult` 420 giây, 1/1 stream, drift 0. Test vẫn đi qua serializer, validator,
cache, EDL, state machine, audit và publish thật; chỉ thay network/FFmpeg boundary.

- [ ] **Step 4: Chạy toàn bộ verification**

Run: `uv run pytest -q`

Run: `uv run ruff check .`

Run: `git diff --check`

Expected: toàn bộ test PASS, Ruff không có lỗi, diff check exit 0.

- [ ] **Step 5: Kiểm tra phạm vi và dữ liệu người dùng**

Run: `git status --short`

Expected: chỉ file mã/test/docs dự kiến thay đổi; `Kho_Anime/` và
`Goi_gui_ChatGPT_Web/` vẫn là dữ liệu người dùng không bị stage hoặc sửa.

- [ ] **Step 6: Commit tích hợp cuối**

```bash
git add src tests Bo_nao_Antigravity README.md pyproject.toml uv.lock
git commit -m "feat: complete Antigravity-first anime review pipeline"
```

- [ ] **Step 7: Bàn giao prompt BLACK TORCH mà không tự chạy Antigravity**

Tạo/reuse một run revision bằng `run_episode.py start --revision`, rồi đưa người dùng
đúng nội dung `PROMPT_MOT_LAN_CHAY.md` đã điền đường dẫn job. Dừng để người dùng dán
prompt cho Antigravity; Codex không tự dựng lại video và không sửa artifact tập.

---

## Self-Review Result

- Spec coverage: atomic beat, role ownership, targeted evidence, critic separation,
  TTS cache, proxy-first, audit 0.90, policy hash, cleanup và one-run flow đều có task.
- Scope: các task phụ thuộc tuần tự trong cùng pipeline; không tách thành dự án riêng.
- Type consistency: dùng thống nhất `AtomicStoryboard`, `AtomicTtsManifest`,
  `CriticReviewDocument`, `build_atomic_edl` và `build_atomic_engine_audit`.
- Dependency check: không thêm dependency ngoài trong kế hoạch này.
