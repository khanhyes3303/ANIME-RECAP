# Semantic Fail-Closed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chặn các đường lách semantic đã tạo ra video BLACK TORCH sai hình–lời dù báo PASS.

**Architecture:** Siết storyboard ngay tại biên load, dùng SOURCE/PROGRAM anchor do
engine tự sinh làm bằng chứng bắt buộc, và buộc critic video trả verdict có cấu trúc.
Final audit nhận anchor thật và run state thay vì tin note/finding rỗng của agent.

**Tech Stack:** Python 3.13, dataclasses, strict JSON loader, pytest, Ruff, FFmpeg.

**Spec:** `docs/superpowers/specs/2026-08-29-semantic-fail-closed-design.md`

## Global Constraints

- Codex chỉ sửa bộ não/engine/test/docs; không render tập hoặc sửa `Kho_Anime`.
- Antigravity vẫn là operator duy nhất của từng tập.
- Chỉ TTS `BV074_streaming`; không source audio, BGM, speed, freeze, loop, MCP/repo mới.
- Mỗi hành vi mới phải có test RED được quan sát trước production code.

---

### Task 1: Storyboard timing và evidence membership

**Files:**
- Modify: `src/anime_review_mvp/atomic.py`
- Modify: `src/anime_review_mvp/models.py`
- Modify: `tests/unit/test_atomic.py`

**Interfaces:**
- Consumes: `AtomicStoryboard`, `Shot`, `TruthDocument`.
- Produces: `load_atomic_storyboard(...)` fail-closed với evidence/timing thật.

- [ ] **Step 1: Viết test RED cho frame ngoài range và action window giả**

```python
def test_storyboard_rejects_frame_evidence_outside_selected_shots(tmp_path: Path) -> None:
    payload = atomic_payload(frame_evidence=["shot-999.jpg"])
    with pytest.raises(MvpError, match="frame evidence.*selected shot"):
        load_atomic_storyboard(write(tmp_path, payload), truth(), shots(), 10_000)

def test_storyboard_rejects_one_second_window_for_long_action_voice(tmp_path: Path) -> None:
    payload = atomic_payload(estimated_tts_ms=9_000, action_window=(1_000, 2_000))
    with pytest.raises(MvpError, match="action window.*TTS"):
        load_atomic_storyboard(write(tmp_path, payload), truth(), shots(), 10_000)
```

- [ ] **Step 2: Chạy test và xác nhận fail vì validator hiện chỉ kiểm tra tồn tại.**
- [ ] **Step 3: Cài membership, lead 750 ms và coverage action 35%/1.500 ms.**
- [ ] **Step 4: Chạy `uv run pytest tests/unit/test_atomic.py -v` và commit.**

### Task 2: Engine-owned anchor và critic có cấu trúc

**Files:**
- Modify: `src/anime_review_mvp/models.py`
- Modify: `src/anime_review_mvp/media.py`
- Modify: `src/anime_review_mvp/atomic.py`
- Modify: `tests/unit/test_atomic.py`
- Modify: `tests/unit/test_media.py`

**Interfaces:**
- Produces: `extract_atomic_source_anchors(...)`,
  `validate_critic_evidence(review, storyboard, source_anchors, program_anchors=None)`.

- [ ] **Step 1: Viết test RED yêu cầu SCRIPT đủ SOURCE anchors và VIDEO đủ cả hai timeline.**
- [ ] **Step 2: Viết test RED chặn critic lặp cùng observation cho từ ba beat.**
- [ ] **Step 3: Mở rộng `CriticBeatReview` với `observed_visual`,
  `narration_summary`, `sync_verdict`; verdict VIDEO khác MATCH tự sinh finding.**
- [ ] **Step 4: Cài extractor SOURCE cho `AtomicStoryboard`, chạy test và commit.**

### Task 3: Wire CLI và final audit fail-closed

**Files:**
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/audit.py`
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `tests/unit/test_cli_antigravity.py`
- Modify: `tests/unit/test_atomic_edl_audit.py`

**Interfaces:**
- `build_atomic_engine_audit(..., source_anchors, program_anchors, stage_metrics_count)`.

- [ ] **Step 1: Viết test RED chứng minh critic tự khai frame không đủ để PASS.**
- [ ] **Step 2: Viết test RED chặn final audit khi stage metrics trống.**
- [ ] **Step 3: Storyboard validation trích SOURCE anchors; critic validators tải manifest;
  final render trích lại PROGRAM anchors từ final candidate.**
- [ ] **Step 4: Audit kiểm tra đủ START/MIDDLE/END mỗi range, verdict, evidence và metrics.**
- [ ] **Step 5: Chạy test CLI/audit và commit.**

### Task 4: Vùng loại bỏ và chỉ dẫn Antigravity

**Files:**
- Modify: `src/anime_review_mvp/models.py`
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Modify: `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md`
- Modify: `Bo_nao_Antigravity/mau/critic_script.json`
- Modify: `Bo_nao_Antigravity/mau/critic_video.json`
- Modify: `README.md`
- Modify: `tests/unit/test_models.py`
- Modify: `tests/unit/test_antigravity_contract.py`

**Interfaces:**
- Source kinds mới: `TITLE_CARD`, `EYECATCH`, `STUDIO_LOGO`.
- Prompt nhận `<run_dir>` như tham số bắt buộc và hiển thị ví dụ BLACK TORCH rõ ràng.

- [ ] **Step 1: Viết test RED cho source kinds và prompt không còn hứa dán placeholder.**
- [ ] **Step 2: Cập nhật brain: cấm script duration-driven, cấm critic sinh bằng loop,
  bắt mở contact sheet từng beat và ghi verdict riêng.**
- [ ] **Step 3: Cập nhật JSON mẫu/README, chạy test contract và commit.**

### Task 5: Regression và verification toàn bộ

**Files:**
- Modify: `tests/acceptance/test_episode_pipeline.py`
- Modify: fixtures atomic/critic liên quan.

**Interfaces:**
- Acceptance fixture đi qua source anchors → critic script → proxy/program anchors →
  critic video → final audit/publish.

- [ ] **Step 1: Viết regression fixture mô phỏng đúng lỗi 47 beat một-giây/canned critic.**
- [ ] **Step 2: Xác nhận fixture lỗi bị chặn và fixture tốt hoàn tất.**
- [ ] **Step 3: Chạy `uv run pytest -q`, `uv run ruff check .`, `git diff --check`.**
- [ ] **Step 4: Kiểm tra không có thay đổi trong dữ liệu/video người dùng và commit tích hợp.**

## Self-Review Result

- Từng nguyên nhân đã chứng minh có một gate/test tương ứng.
- Không dùng quality score giả hoặc chỉ grep prose để chứng minh semantic sync.
- Không thêm dependency; anchor dùng FFmpeg có sẵn.
- Không tuyên bố semantic hoàn hảo tuyệt đối; PASS chỉ mạnh hơn khi evidence thật đầy đủ.

