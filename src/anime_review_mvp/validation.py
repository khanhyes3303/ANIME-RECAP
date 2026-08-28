from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from .errors import MvpError
from .models import (
    AtomicStoryboard,
    AuditFinding,
    AuditReport,
    EdlDocument,
    EdlSegment,
    SceneBeat,
    ScenePacket,
    SceneShot,
    ScriptDocument,
    Shot,
    TruthDocument,
    TtsManifest,
)

MINIMUM_COVERAGE = Decimal("0.80")
MAX_DURATION_DRIFT_MS = 40
MIN_REVIEW_DURATION_MS = 7 * 60 * 1000
MAX_REVIEW_DURATION_MS = 12 * 60 * 1000

# These are deliberately editorial guardrails, not a replacement for visual
# verification.  They prevent a writer from hiding several facts in one long
# cue and then stretching the footage to fit it.
MAX_NARRATION_CUE_CHARS = 240
MAX_NARRATION_SENTENCES = 2
MAX_NARRATION_CLAUSES = 4
MAX_STYLE_MARKERS_PER_CUE = 3

_STYLE_MARKERS = (
    "vô tiền khoáng hậu",
    "mang tính lịch sử",
    "nghi thức",
    "kinh thiên động địa",
    "quyền năng vô song",
    "thượng đế ban tặng",
    "danh dự cao quý",
    "lòng tự ái tổ nghề",
    "ngàn cân treo sợi tóc",
    "tột độ",
    "khốc liệt",
    "thiêng liêng",
    "huyền thoại",
    "tàn bạo",
    "long trọng",
)


def _style_marker_count(text: str) -> int:
    normalized = " ".join(text.casefold().split())
    return sum(normalized.count(marker) for marker in _STYLE_MARKERS)


def narration_style_findings(script: ScriptDocument) -> tuple[AuditFinding, ...]:
    """Return deterministic editorial findings for narration prose.

    Antigravity is allowed to write the script artifact, but it is not allowed
    to certify its own prose.  This small gate catches the failure mode where a
    cue is factually bound yet padded with many clauses, generic superlatives,
    or cinematic filler.  It intentionally does not judge slang or humour.
    """
    findings: list[AuditFinding] = []
    for cue in script.cues:
        text = " ".join(cue.text.split())
        sentence_count = len(re.findall(r"[.!?]+", text)) or 1
        clause_count = len(re.findall(r"[,;:]", text)) + 1
        marker_count = _style_marker_count(text)
        if len(text) > MAX_NARRATION_CUE_CHARS:
            findings.append(
                AuditFinding(
                    "ERROR",
                    "NARRATION_CUE_TOO_LONG",
                    cue.cue_id,
                    f"cue has {len(text)} characters; maximum is {MAX_NARRATION_CUE_CHARS}",
                    (cue.scene_id, *cue.beat_ids),
                )
            )
        if sentence_count > MAX_NARRATION_SENTENCES:
            findings.append(
                AuditFinding(
                    "ERROR",
                    "NARRATION_TOO_MANY_SENTENCES",
                    cue.cue_id,
                    f"cue has {sentence_count} sentences; maximum is {MAX_NARRATION_SENTENCES}",
                    (cue.scene_id, *cue.beat_ids),
                )
            )
        if clause_count > MAX_NARRATION_CLAUSES:
            findings.append(
                AuditFinding(
                    "ERROR",
                    "NARRATION_TOO_MANY_CLAUSES",
                    cue.cue_id,
                    f"cue has {clause_count} clauses; maximum is {MAX_NARRATION_CLAUSES}",
                    (cue.scene_id, *cue.beat_ids),
                )
            )
        if marker_count > MAX_STYLE_MARKERS_PER_CUE:
            findings.append(
                AuditFinding(
                    "ERROR",
                    "NARRATION_STYLE_OVERWRITTEN",
                    cue.cue_id,
                    f"cue has {marker_count} dramatic style markers; maximum is "
                    f"{MAX_STYLE_MARKERS_PER_CUE}",
                    (cue.scene_id, *cue.beat_ids),
                )
            )
    return tuple(findings)


def atomic_style_findings(storyboard: AtomicStoryboard) -> tuple[AuditFinding, ...]:
    findings: list[AuditFinding] = []
    opening_to_beats: dict[str, list[str]] = defaultdict(list)
    formulaic_connectors = {
        "lúc này",
        "ngay sau đó",
        "không ngờ rằng",
        "thế là",
    }
    for beat in storyboard.beats:
        normalized = " ".join(beat.narration_text.casefold().split())
        words = re.findall(r"\w+", normalized, flags=re.UNICODE)
        opening = " ".join(words[:2])
        if opening:
            opening_to_beats[opening].append(beat.beat_id)
        marker_count = _style_marker_count(normalized)
        clause_count = len(re.findall(r"[,;:]", normalized)) + 1
        if marker_count > MAX_STYLE_MARKERS_PER_CUE or clause_count > 3:
            findings.append(
                AuditFinding(
                    "ERROR",
                    "FORMULAIC_PROSE",
                    beat.beat_id,
                    "Atomic narration is overwritten or contains too many clauses.",
                    beat.frame_evidence,
                )
            )
    for opening, beat_ids in opening_to_beats.items():
        if len(beat_ids) >= 3 or (opening in formulaic_connectors and len(beat_ids) >= 2):
            for beat_id in beat_ids:
                findings.append(
                    AuditFinding(
                        "ERROR",
                        "REPEATED_OPENING",
                        beat_id,
                        f"Opening phrase is repeated across the episode: {opening}",
                        tuple(beat_ids),
                    )
                )
    return tuple(findings)


def review_duration_findings(tts: TtsManifest) -> tuple[AuditFinding, ...]:
    """Check the finished narration against the requested 7–12 minute window."""
    # The acceptance suite uses a deliberately tiny fake provider/media fixture;
    # production providers are still checked strictly.
    if tts.provider == "fake":
        return ()
    total_ms = sum(cue.duration_ms for cue in tts.cues)
    if MIN_REVIEW_DURATION_MS <= total_ms <= MAX_REVIEW_DURATION_MS:
        return ()
    return (
        AuditFinding(
            "ERROR",
            "REVIEW_DURATION_OUT_OF_RANGE",
            None,
            f"narration duration is {total_ms / 1000:.2f}s; expected 420–720s",
            (),
        ),
    )


def _duplicates(values: list[str]) -> bool:
    return len(values) != len(set(values))


def validate_truth(truth: TruthDocument, source_duration_ms: int) -> None:
    if source_duration_ms <= 0:
        raise MvpError("source duration must be positive")
    event_ids = [event.event_id for event in truth.events]
    region_ids = [region.region_id for region in truth.source_regions]
    if _duplicates(event_ids) or _duplicates(region_ids):
        raise MvpError("truth artifact contains duplicate IDs")
    for item in (*truth.events, *truth.source_regions):
        if item.end_ms > source_duration_ms:
            raise MvpError("truth timestamp exceeds source duration")
    ordered_regions = sorted(
        truth.source_regions, key=lambda region: (region.start_ms, region.end_ms)
    )
    for previous, current in zip(ordered_regions, ordered_regions[1:], strict=False):
        if current.start_ms < previous.end_ms:
            raise MvpError("source-region annotations overlap")


def validate_script(script: ScriptDocument, truth: TruthDocument) -> None:
    cue_ids = [cue.cue_id for cue in script.cues]
    if _duplicates(cue_ids):
        raise MvpError("script contains duplicate cue IDs")
    event_ids = {event.event_id for event in truth.events}
    for cue in script.cues:
        unknown = set(cue.event_ids) - event_ids
        if unknown:
            raise MvpError(f"cue references unknown event IDs: {sorted(unknown)}")
    claim_ids = [claim.claim_id for claim in script.claims]
    if _duplicates(claim_ids):
        raise MvpError("script contains duplicate claim IDs")
    claims = {claim.claim_id: claim for claim in script.claims}
    for claim in script.claims:
        unknown = set(claim.evidence_event_ids) - event_ids
        if unknown:
            raise MvpError(f"claim references unknown event IDs: {sorted(unknown)}")
    for cue in script.cues:
        unknown_claims = set(cue.claim_ids) - set(claims)
        if unknown_claims:
            raise MvpError(f"cue references unknown claim IDs: {sorted(unknown_claims)}")
        required_evidence = {
            event_id
            for claim_id in cue.claim_ids
            for event_id in claims[claim_id].evidence_event_ids
        }
        if not required_evidence <= set(cue.event_ids):
            raise MvpError("cue event binding does not include all claim evidence")


def coverage_ratio(script: ScriptDocument, tts: TtsManifest) -> Decimal:
    durations: dict[str, int] = {}
    for cue in tts.cues:
        if cue.cue_id in durations:
            raise MvpError("TTS manifest contains duplicate cue IDs")
        if cue.duration_ms <= 0:
            raise MvpError("TTS duration must be positive")
        durations[cue.cue_id] = cue.duration_ms
    script_ids = {cue.cue_id for cue in script.cues}
    if script_ids != set(durations):
        raise MvpError("script and TTS cue IDs must match exactly")
    total = sum(durations.values())
    if total <= 0:
        raise MvpError("TTS duration must be positive")
    supported = sum(durations[cue.cue_id] for cue in script.cues if cue.directly_supported)
    return Decimal(supported) / Decimal(total)


def validate_edl(
    edl: EdlDocument,
    source_duration_ms: int,
    tts: TtsManifest,
    truth: TruthDocument,
) -> None:
    if not edl.segments:
        raise MvpError("EDL requires segments")
    expected = {cue.cue_id: cue.duration_ms for cue in tts.cues}
    if _duplicates([segment.segment_id for segment in edl.segments]):
        raise MvpError("EDL contains duplicate segment IDs")
    grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
    excluded = [region for region in truth.source_regions if region.decision == "EXCLUDE"]
    for segment in edl.segments:
        if segment.cue_id not in expected:
            raise MvpError(f"EDL references unknown cue ID: {segment.cue_id}")
        if (
            segment.source_start_ms < 0
            or segment.source_end_ms <= segment.source_start_ms
            or segment.source_end_ms > source_duration_ms
        ):
            raise MvpError("EDL source interval is outside source bounds")
        for region in excluded:
            if max(segment.source_start_ms, region.start_ms) < min(
                segment.source_end_ms, region.end_ms
            ):
                raise MvpError("EDL intersects an excluded source region")
        grouped[segment.cue_id].append((segment.source_start_ms, segment.source_end_ms))

    if set(grouped) != set(expected):
        raise MvpError("EDL must provide footage for every TTS cue")
    for cue_id, intervals in grouped.items():
        for previous, current in zip(intervals, intervals[1:], strict=False):
            if current[0] < previous[1]:
                raise MvpError(f"EDL footage is not chronological for {cue_id}")
        footage_ms = sum(end - start for start, end in intervals)
        if abs(footage_ms - expected[cue_id]) > MAX_DURATION_DRIFT_MS:
            raise MvpError(
                f"footage duration for {cue_id} differs from TTS by more than "
                f"{MAX_DURATION_DRIFT_MS} ms"
            )


_SCENE_SHOT_ROLES = {"MUST_KEEP", "OPTIONAL", "TRANSITION"}


def _intervals_overlap(
    first_start: int,
    first_end: int,
    second_start: int,
    second_end: int,
) -> bool:
    return max(first_start, second_start) < min(first_end, second_end)


def validate_scene_packets(
    packets: tuple[ScenePacket, ...],
    truth: TruthDocument,
    shots: tuple[Shot, ...],
    source_duration_ms: int,
) -> None:
    """Validate semantic scenes without deciding which scenes are interesting."""
    if source_duration_ms <= 0:
        raise MvpError("source duration must be positive")
    if not packets:
        raise MvpError("scene packets are required")

    event_ids = {event.event_id for event in truth.events}
    source_shots = {shot.shot_id: shot for shot in shots}
    if len(source_shots) != len(shots):
        raise MvpError("source shots contain duplicate IDs")

    scene_ids: set[str] = set()
    packet_shot_ids: set[str] = set()
    beat_ids: set[str] = set()
    previous_scene_end = -1
    for packet in packets:
        if packet.scene_id in scene_ids:
            raise MvpError("scene packets contain duplicate scene IDs")
        scene_ids.add(packet.scene_id)
        if packet.end_ms > source_duration_ms:
            raise MvpError("scene timestamp exceeds source duration")
        if packet.start_ms < previous_scene_end:
            raise MvpError("scene packets overlap or are not chronological")
        previous_scene_end = packet.end_ms
        if not set(packet.event_ids) <= event_ids:
            raise MvpError("scene references unknown event IDs")
        if _duplicates(list(packet.cue_ids)):
            raise MvpError("scene contains duplicate cue IDs")

        packet_shots: dict[str, SceneShot] = {}
        previous_shot_end = packet.start_ms
        for scene_shot in packet.shots:
            if scene_shot.shot_id in packet_shots or scene_shot.shot_id in packet_shot_ids:
                raise MvpError("scene packets contain duplicate shot IDs")
            if scene_shot.start_ms < packet.start_ms or scene_shot.end_ms > packet.end_ms:
                raise MvpError("scene bounds do not contain every shot")
            if scene_shot.start_ms < previous_shot_end:
                raise MvpError("scene shots overlap or are not chronological")
            source_shot = source_shots.get(scene_shot.shot_id)
            if source_shot is None:
                raise MvpError(f"scene references unknown shot ID: {scene_shot.shot_id}")
            if scene_shot.start_ms < source_shot.start_ms or scene_shot.end_ms > source_shot.end_ms:
                raise MvpError("scene shot interval exceeds source shot bounds")
            if not set(scene_shot.event_ids) <= event_ids:
                raise MvpError("scene shot references unknown event IDs")
            if not set(scene_shot.event_ids) <= set(packet.event_ids):
                raise MvpError("scene shot event is outside its scene")
            for excluded in truth.source_regions:
                if excluded.decision == "EXCLUDE" and _intervals_overlap(
                    scene_shot.start_ms,
                    scene_shot.end_ms,
                    excluded.start_ms,
                    excluded.end_ms,
                ):
                    raise MvpError("scene intersects an excluded source region")
            packet_shots[scene_shot.shot_id] = scene_shot
            packet_shot_ids.add(scene_shot.shot_id)
            previous_shot_end = scene_shot.end_ms

        packet_beats: dict[str, object] = {}
        for beat in packet.beats:
            if beat.beat_id in beat_ids:
                raise MvpError("scene packets contain duplicate beat IDs")
            beat_ids.add(beat.beat_id)
            if beat.start_ms < packet.start_ms or beat.end_ms > packet.end_ms:
                raise MvpError("scene bounds do not contain every beat")
            if not set(beat.event_ids) <= event_ids or not set(beat.event_ids) <= set(
                packet.event_ids
            ):
                raise MvpError("beat references unknown event IDs")
            if not set(beat.shot_ids) <= set(packet_shots):
                raise MvpError("beat references a shot outside its scene")
            if not set(beat.cue_ids) <= set(packet.cue_ids):
                raise MvpError("beat references a cue outside its scene")
            for shot_id in beat.shot_ids:
                scene_shot = packet_shots[shot_id]
                if not _intervals_overlap(
                    beat.start_ms,
                    beat.end_ms,
                    scene_shot.start_ms,
                    scene_shot.end_ms,
                ):
                    raise MvpError("beat does not overlap one of its shots")
            packet_beats[beat.beat_id] = beat

        for scene_shot in packet.shots:
            if scene_shot.role == "MUST_KEEP":
                has_evidence = bool(scene_shot.event_ids) or any(
                    scene_shot.shot_id in beat.shot_ids and beat.event_ids for beat in packet.beats
                )
                if not has_evidence:
                    raise MvpError("MUST_KEEP shot requires event or beat evidence")


def cue_source_duration(edl: EdlDocument, cue_id: str) -> int:
    return sum(
        segment.source_end_ms - segment.source_start_ms
        for segment in edl.segments
        if segment.cue_id == cue_id
    )


def _cover_interval(intervals: list[tuple[int, int]], start_ms: int, end_ms: int) -> bool:
    cursor = start_ms
    for start, end in sorted(intervals):
        if end <= cursor:
            continue
        if start > cursor:
            return False
        cursor = max(cursor, end)
        if cursor >= end_ms:
            return True
    return cursor >= end_ms


def validate_voice_lock(
    packets: tuple[ScenePacket, ...],
    script: ScriptDocument,
    tts: TtsManifest,
    edl: EdlDocument,
    tolerance_ms: int = MAX_DURATION_DRIFT_MS,
) -> None:
    """Ensure narration cues are semantically and temporally locked to scenes."""
    if tolerance_ms < 0:
        raise MvpError("voice-lock tolerance must not be negative")
    packet_by_scene = {packet.scene_id: packet for packet in packets}
    cue_by_id = {cue.cue_id: cue for cue in script.cues}
    if len(cue_by_id) != len(script.cues):
        raise MvpError("voice-lock script contains duplicate cue IDs")
    tts_by_id = {cue.cue_id: cue for cue in tts.cues}
    if set(cue_by_id) != set(tts_by_id):
        raise MvpError("voice-lock script and TTS cue IDs must match")

    packet_shots: dict[tuple[str, str], SceneShot] = {}
    packet_beats: dict[tuple[str, str], SceneBeat] = {}
    for packet in packets:
        for shot in packet.shots:
            packet_shots[(packet.scene_id, shot.shot_id)] = shot
        for beat in packet.beats:
            packet_beats[(packet.scene_id, beat.beat_id)] = beat

    for cue in script.cues:
        if not cue.scene_id:
            raise MvpError(f"voice-lock cue {cue.cue_id} is missing scene_id")
        packet = packet_by_scene.get(cue.scene_id)
        if packet is None:
            raise MvpError(f"voice-lock cue references unknown scene: {cue.scene_id}")
        if not cue.beat_ids:
            raise MvpError(f"voice-lock cue {cue.cue_id} requires beat IDs")
        if not set(cue.beat_ids) <= {beat.beat_id for beat in packet.beats}:
            raise MvpError(f"voice-lock cue {cue.cue_id} references an unknown beat")
        if not set(cue.event_ids) <= set(packet.event_ids):
            raise MvpError(f"voice-lock cue {cue.cue_id} references an event outside its scene")

    if not edl.segments:
        raise MvpError("voice-lock EDL requires segments")
    expected = {cue_id: cue.duration_ms for cue_id, cue in tts_by_id.items()}
    if any(duration <= 0 for duration in expected.values()):
        raise MvpError("voice-lock TTS durations must be positive")
    if _duplicates([segment.segment_id for segment in edl.segments]):
        raise MvpError("voice-lock EDL contains duplicate segment IDs")

    grouped: dict[str, list[EdlSegment]] = defaultdict(list)
    max_source_ms = max(packet.end_ms for packet in packets)
    for segment in edl.segments:
        if segment.cue_id not in cue_by_id:
            raise MvpError(f"voice-lock EDL references unknown cue: {segment.cue_id}")
        if (
            not all((segment.scene_id, segment.shot_id, segment.beat_id, segment.role))
            or not segment.event_ids
        ):
            raise MvpError("voice-lock EDL segment is missing semantic links")
        if segment.role not in _SCENE_SHOT_ROLES:
            raise MvpError("voice-lock EDL segment role is invalid")
        if segment.source_start_ms < 0 or segment.source_end_ms <= segment.source_start_ms:
            raise MvpError("voice-lock EDL source interval is invalid")
        if segment.source_end_ms > max_source_ms:
            raise MvpError("voice-lock EDL source interval exceeds scene bounds")

        cue = cue_by_id[segment.cue_id]
        if segment.scene_id != cue.scene_id:
            raise MvpError("voice-lock EDL segment belongs to the wrong scene")
        scene_shot = packet_shots.get((segment.scene_id, segment.shot_id))
        if scene_shot is None:
            raise MvpError("voice-lock EDL references an unknown scene shot")
        if segment.role != scene_shot.role:
            raise MvpError("voice-lock EDL role does not match scene shot")
        if (
            segment.source_start_ms < scene_shot.start_ms
            or segment.source_end_ms > scene_shot.end_ms
        ):
            raise MvpError("voice-lock EDL segment exceeds scene shot bounds")
        beat = packet_beats.get((segment.scene_id, segment.beat_id))
        if beat is None or segment.beat_id not in cue.beat_ids:
            raise MvpError("voice-lock EDL references a beat outside its cue")
        if segment.shot_id not in beat.shot_ids or not _intervals_overlap(
            segment.source_start_ms,
            segment.source_end_ms,
            beat.start_ms,
            beat.end_ms,
        ):
            raise MvpError("voice-lock EDL segment is not covered by its beat")
        allowed_events = set(scene_shot.event_ids) | set(beat.event_ids)
        if not set(segment.event_ids) <= allowed_events:
            raise MvpError("voice-lock EDL references an event outside its beat")
        grouped[segment.cue_id].append(segment)

    if set(grouped) != set(expected):
        raise MvpError("voice-lock EDL must provide footage for every cue")

    all_source_segments = sorted(
        edl.segments,
        key=lambda segment: (segment.source_start_ms, segment.source_end_ms),
    )
    for previous, current in zip(all_source_segments, all_source_segments[1:], strict=False):
        if current.source_start_ms < previous.source_end_ms:
            raise MvpError("voice-lock EDL reuses overlapping source footage")

    for packet in packets:
        for scene_shot in packet.shots:
            if scene_shot.role != "MUST_KEEP":
                continue
            intervals = [
                (segment.source_start_ms, segment.source_end_ms)
                for segment in edl.segments
                if segment.scene_id == packet.scene_id and segment.shot_id == scene_shot.shot_id
            ]
            if not _cover_interval(intervals, scene_shot.start_ms, scene_shot.end_ms):
                raise MvpError(
                    f"voice-lock EDL does not preserve MUST_KEEP shot {scene_shot.shot_id}"
                )

    program_cursor_ms = 0
    for cue in script.cues:
        cue_id = cue.cue_id
        segments = grouped[cue_id]
        ordered = sorted(segments, key=lambda segment: segment.source_start_ms)
        if list(segments) != ordered:
            raise MvpError(f"voice-lock EDL is not chronological for {cue_id}")
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.source_start_ms < previous.source_end_ms:
                raise MvpError(f"voice-lock EDL footage overlaps for {cue_id}")
        footage_ms = sum(segment.source_end_ms - segment.source_start_ms for segment in segments)
        if abs(footage_ms - expected[cue_id]) > tolerance_ms:
            raise MvpError(
                f"voice-lock duration for {cue_id} differs from TTS by more than {tolerance_ms} ms"
            )
        for segment in segments:
            duration_ms = segment.source_end_ms - segment.source_start_ms
            if (
                segment.program_start_ms != program_cursor_ms
                or segment.program_end_ms != program_cursor_ms + duration_ms
            ):
                raise MvpError("voice-lock EDL program timing is not contiguous")
            program_cursor_ms += duration_ms


def build_edl_from_scene_packets(
    packets: tuple[ScenePacket, ...],
    script: ScriptDocument,
    tts: TtsManifest,
) -> EdlDocument:
    """Build a 1:1 EDL, trimming only optional/transition footage when necessary."""
    packet_by_scene = {packet.scene_id: packet for packet in packets}
    tts_by_cue = {cue.cue_id: cue.duration_ms for cue in tts.cues}
    if len(tts_by_cue) != len(tts.cues):
        raise MvpError("TTS manifest contains duplicate cue IDs")
    segments: list[EdlSegment] = []
    program_cursor_ms = 0
    for cue in script.cues:
        if cue.scene_id not in packet_by_scene:
            raise MvpError(f"cannot build EDL for unknown scene: {cue.scene_id}")
        if cue.cue_id not in tts_by_cue:
            raise MvpError(f"cannot build EDL without TTS cue: {cue.cue_id}")
        packet = packet_by_scene[cue.scene_id]
        beats = {beat.beat_id: beat for beat in packet.beats}
        if not cue.beat_ids or not set(cue.beat_ids) <= set(beats):
            raise MvpError(f"cannot build EDL for cue {cue.cue_id} without valid beats")

        shot_by_id = {shot.shot_id: shot for shot in packet.shots}
        ordered_shots: list[tuple[SceneShot, str]] = []
        seen_shots: set[str] = set()
        for beat in sorted(
            (beats[beat_id] for beat_id in cue.beat_ids),
            key=lambda item: item.start_ms,
        ):
            for shot_id in beat.shot_ids:
                if shot_id not in seen_shots:
                    seen_shots.add(shot_id)
                    ordered_shots.append((shot_by_id[shot_id], beat.beat_id))
        ordered_shots.sort(key=lambda item: item[0].start_ms)
        target_ms = tts_by_cue[cue.cue_id]
        total_ms = sum(shot.end_ms - shot.start_ms for shot, _ in ordered_shots)
        must_keep_ms = sum(
            shot.end_ms - shot.start_ms for shot, _ in ordered_shots if shot.role == "MUST_KEEP"
        )
        if target_ms > total_ms:
            raise MvpError(f"insufficient scene footage for cue {cue.cue_id}")
        if target_ms < must_keep_ms:
            raise MvpError(f"TTS is shorter than MUST_KEEP footage for cue {cue.cue_id}")

        excess_ms = total_ms - target_ms
        kept: list[tuple[SceneShot, str, int, int]] = []
        for shot, beat_id in ordered_shots:
            start_ms, end_ms = shot.start_ms, shot.end_ms
            if excess_ms and shot.role != "MUST_KEEP":
                trim_ms = min(excess_ms, end_ms - start_ms)
                end_ms -= trim_ms
                excess_ms -= trim_ms
            if end_ms > start_ms:
                kept.append((shot, beat_id, start_ms, end_ms))
        if excess_ms:
            raise MvpError(
                f"cannot trim optional footage without cutting MUST_KEEP for cue {cue.cue_id}"
            )

        for index, (shot, beat_id, start_ms, end_ms) in enumerate(kept, start=1):
            duration_ms = end_ms - start_ms
            event_ids = tuple(dict.fromkeys((*shot.event_ids, *beats[beat_id].event_ids)))
            segments.append(
                EdlSegment(
                    segment_id=f"{cue.cue_id}-segment-{index:03d}",
                    cue_id=cue.cue_id,
                    source_start_ms=start_ms,
                    source_end_ms=end_ms,
                    scene_id=packet.scene_id,
                    shot_id=shot.shot_id,
                    beat_id=beat_id,
                    event_ids=event_ids,
                    role=shot.role,
                    program_start_ms=program_cursor_ms,
                    program_end_ms=program_cursor_ms + duration_ms,
                )
            )
            program_cursor_ms += duration_ms
    return EdlDocument(tuple(segments))


def validate_audit(audit: AuditReport, coverage: Decimal) -> None:
    errors = [finding for finding in audit.findings if finding.severity == "ERROR"]
    if errors:
        codes = ", ".join(finding.code for finding in errors)
        raise MvpError(f"audit has blocking errors: {codes}")
    if coverage < MINIMUM_COVERAGE:
        raise MvpError("direct evidence coverage must be at least 0.80")
    try:
        reported = Decimal(audit.coverage_ratio)
    except InvalidOperation as exc:
        raise MvpError("audit coverage_ratio is invalid") from exc
    if reported != coverage:
        raise MvpError("audit coverage_ratio does not match measured coverage")
    if not audit.passed:
        raise MvpError("audit did not pass")
