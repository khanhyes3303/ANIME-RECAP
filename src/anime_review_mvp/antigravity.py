from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import MvpError
from .jsonio import dump_json, load_json
from .models import (
    AuditReport,
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
    script: str
    audit: str


@dataclass(frozen=True, slots=True)
class OperatorJob:
    anime: str
    season: int
    episode: int
    source: SourceRef
    transcript: TranscriptDocument
    shots: tuple[Shot, ...]
    required_outputs: RequiredOutputs


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
            script=str(paths.script_dir / "kich_ban_review.json"),
            audit=str(paths.report_dir / "kiem_dinh.json"),
        ),
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
    return script


def load_audit(path: Path) -> AuditReport:
    audit = load_json(path, AuditReport)
    if audit.passed and any(finding.severity == "ERROR" for finding in audit.findings):
        raise MvpError("audit cannot PASS while an ERROR finding remains")
    return audit
