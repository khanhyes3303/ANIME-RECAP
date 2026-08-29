from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .errors import MvpError
from .jsonio import dump_json, load_json
from .models import (
    AuditReport,
    ScenePacketDocument,
    ScriptDocument,
    Shot,
    SourceRef,
    TranscriptDocument,
    TruthDocument,
)
from .workspace import JobPaths


@dataclass(frozen=True, slots=True)
class RequiredOutputs:
    truth: str
    scene_packets: str
    storyboard: str
    critic_script: str
    critic_video: str


@dataclass(frozen=True, slots=True)
class WritePolicy:
    allowed_write_roots: tuple[str, ...]
    read_only_roots: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperatorJob:
    anime: str
    season: int
    episode: int
    source: SourceRef
    transcript: TranscriptDocument
    shots: tuple[Shot, ...]
    required_outputs: RequiredOutputs
    write_policy: WritePolicy
    policy_sha256: str
    inspection_frames_dir: str


def calculate_policy_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    fixed_paths = (
        Path("Bo_nao_Antigravity/GEMINI.md"),
        Path("Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md"),
        Path("pyproject.toml"),
        Path("uv.lock"),
        Path("run_episode.py"),
    )
    discovered = (
        *(path.relative_to(root) for path in (root / "src" / "anime_review_mvp").glob("*.py")),
        *(
            path.relative_to(root)
            for path in (root / "Bo_nao_Antigravity").rglob("*")
            if path.is_file()
        ),
    )
    relative_paths = tuple(
        sorted(set((*fixed_paths, *discovered)), key=lambda item: item.as_posix())
    )
    for relative in relative_paths:
        path = root / relative
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(path.read_bytes() if path.is_file() else b"<missing>")
    return digest.hexdigest()


def render_operator_prompt(run_dir: Path, template_path: Path) -> str:
    placeholder = r"<ĐƯỜNG_DẪN_RUN>\cong_viec_antigravity.json"
    template = template_path.read_text(encoding="utf-8")
    if placeholder not in template:
        raise MvpError("operator prompt template is missing the run-path placeholder")
    job_path = (run_dir / "cong_viec_antigravity.json").resolve()
    return template.replace(placeholder, str(job_path))


def build_operator_job(
    paths: JobPaths,
    source: SourceRef,
    transcript: TranscriptDocument,
    shots: tuple[Shot, ...],
) -> Path:
    job = OperatorJob(
        anime=paths.key.anime,
        season=paths.key.season,
        episode=paths.key.episode,
        source=source,
        transcript=transcript,
        shots=shots,
        required_outputs=RequiredOutputs(
            truth=str(paths.truth_dir / "su_that_tap_phim.json"),
            scene_packets=str(paths.truth_dir / "scene_packets.json"),
            storyboard=str(paths.script_dir / "atomic_storyboard.json"),
            critic_script=str(paths.report_dir / "critic_script.json"),
            critic_video=str(paths.report_dir / "critic_video.json"),
        ),
        write_policy=WritePolicy(
            allowed_write_roots=tuple(
                str(path.resolve())
                for path in (
                    paths.truth_dir,
                    paths.script_dir,
                    paths.report_dir,
                    paths.temp_dir,
                )
            ),
            read_only_roots=tuple(
                str(path.resolve())
                for path in (
                    paths.source_video,
                    paths.root / "Bo_nao_Antigravity",
                    paths.root / "src",
                    paths.root / "tests",
                    paths.root / "docs",
                    paths.root / ".git",
                    paths.script_dir / "khoa_cau_canh.json",
                    paths.tts_dir,
                    paths.edl_dir,
                    paths.final_dir,
                    paths.episode_dir / "Bao_cao_Codex",
                    paths.report_dir / "kiem_dinh_engine.json",
                )
            ),
        ),
        policy_sha256=calculate_policy_sha256(paths.root),
        inspection_frames_dir=str(paths.cache_dir / "source" / source.sha256 / "frames"),
    )
    output = paths.temp_dir / "cong_viec_antigravity.json"
    dump_json(output, job)
    return output


def _reject_duplicate_ids(values: tuple[object, ...], field: str) -> None:
    ids = [getattr(value, field) for value in values]
    if len(ids) != len(set(ids)):
        raise MvpError(f"duplicate {field} values are forbidden")


def load_truth(path: Path, *, source_duration_ms: int) -> TruthDocument:
    truth = load_json(path, TruthDocument)
    _reject_duplicate_ids(truth.events, "event_id")
    _reject_duplicate_ids(truth.source_regions, "region_id")
    for item in (*truth.events, *truth.source_regions):
        if item.end_ms > source_duration_ms:
            raise MvpError("truth timestamp exceeds source duration")
    return truth


def load_script(path: Path) -> ScriptDocument:
    script = load_json(path, ScriptDocument)
    _reject_duplicate_ids(script.cues, "cue_id")
    if not script.claims:
        raise MvpError("script requires atomic claims")
    _reject_duplicate_ids(script.claims, "claim_id")
    claim_ids = {claim.claim_id for claim in script.claims}
    for cue in script.cues:
        if not cue.scene_id:
            raise MvpError(f"cue {cue.cue_id} requires scene_id")
        if not cue.beat_ids:
            raise MvpError(f"cue {cue.cue_id} requires beat_ids")
        unknown = set(cue.claim_ids) - claim_ids
        if unknown:
            raise MvpError(f"cue references unknown claim IDs: {sorted(unknown)}")
    return script


def load_scene_packets(path: Path) -> ScenePacketDocument:
    document = load_json(path, ScenePacketDocument)
    scene_ids = [packet.scene_id for packet in document.packets]
    if len(scene_ids) != len(set(scene_ids)):
        raise MvpError("scene packet document contains duplicate scene IDs")
    return document


def load_audit(path: Path) -> AuditReport:
    audit = load_json(path, AuditReport)
    if audit.passed and any(finding.severity == "ERROR" for finding in audit.findings):
        raise MvpError("audit cannot PASS while an ERROR finding remains")
    return audit
