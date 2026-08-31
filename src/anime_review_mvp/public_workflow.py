from __future__ import annotations

from enum import StrEnum

from .workflow import Stage


class PublicStage(StrEnum):
    PHAN_TICH = "PHAN_TICH"
    VIET_REVIEW = "VIET_REVIEW"
    TAO_VOICE_VA_KHOP_CANH = "TAO_VOICE_VA_KHOP_CANH"
    DUNG_VIDEO = "DUNG_VIDEO"
    KIEM_TRA = "KIEM_TRA"
    CHO_NGUOI_DUNG_DUYET_PROXY = "CHO_NGUOI_DUNG_DUYET_PROXY"


_PUBLIC_STAGE_BY_INTERNAL = {
    Stage.CHUAN_BI: PublicStage.PHAN_TICH,
    Stage.QUAN_SAT: PublicStage.PHAN_TICH,
    Stage.LAP_TINH_HUONG: PublicStage.PHAN_TICH,
    Stage.LAP_STORYBOARD: PublicStage.PHAN_TICH,
    Stage.TRICH_XUAT_BANG_CHUNG: PublicStage.PHAN_TICH,
    Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG: PublicStage.PHAN_TICH,
    Stage.KIEM_DINH_CHI_MUC_TINH_HUONG: PublicStage.PHAN_TICH,
    Stage.VIET_KICH_BAN: PublicStage.VIET_REVIEW,
    Stage.KIEM_DINH_KICH_BAN: PublicStage.VIET_REVIEW,
    Stage.CODEX_BIEN_TAP: PublicStage.VIET_REVIEW,
    Stage.VIET_LOI: PublicStage.VIET_REVIEW,
    Stage.CHO_GEMINI_SCRIPT: PublicStage.VIET_REVIEW,
    Stage.PHAN_BIEN_KICH_BAN: PublicStage.VIET_REVIEW,
    Stage.CHO_ANTIGRAVITY_TINH_HUONG: PublicStage.VIET_REVIEW,
    Stage.KIEM_DINH_TINH_HUONG: PublicStage.VIET_REVIEW,
    Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG: PublicStage.VIET_REVIEW,
    Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG: PublicStage.VIET_REVIEW,
    Stage.KIEM_DINH_PHAN_BIEN_TINH_HUONG: PublicStage.VIET_REVIEW,
    Stage.KIEM_DINH_MACH_TRUYEN_TOAN_TAP: PublicStage.VIET_REVIEW,
    Stage.TAO_TTS: PublicStage.TAO_VOICE_VA_KHOP_CANH,
    Stage.LAP_EDL: PublicStage.TAO_VOICE_VA_KHOP_CANH,
    Stage.CAN_TTS: PublicStage.TAO_VOICE_VA_KHOP_CANH,
    Stage.CAN_HINH_VOICE: PublicStage.TAO_VOICE_VA_KHOP_CANH,
    Stage.TAO_TTS_TINH_HUONG: PublicStage.TAO_VOICE_VA_KHOP_CANH,
    Stage.LAP_TIMELINE_TINH_HUONG: PublicStage.TAO_VOICE_VA_KHOP_CANH,
    Stage.DUNG_VIDEO: PublicStage.DUNG_VIDEO,
    Stage.DUNG_PROXY: PublicStage.DUNG_VIDEO,
    Stage.DUNG_VIDEO_CUOI: PublicStage.DUNG_VIDEO,
    Stage.DONG_GOI: PublicStage.DUNG_VIDEO,
    Stage.KIEM_DINH_VIDEO: PublicStage.KIEM_TRA,
    Stage.KIEM_DINH_LOCAL: PublicStage.KIEM_TRA,
    Stage.PHAN_BIEN_VIDEO: PublicStage.KIEM_TRA,
    Stage.CHO_GEMINI_PROXY: PublicStage.KIEM_TRA,
    Stage.CHO_GEMINI_FINAL: PublicStage.KIEM_TRA,
    Stage.KIEM_DINH_ENGINE: PublicStage.KIEM_TRA,
    Stage.KIEM_DINH_PROXY: PublicStage.KIEM_TRA,
    Stage.CHO_ANTIGRAVITY_KIEM_DINH_PROXY: PublicStage.KIEM_TRA,
    Stage.KIEM_DINH_PHAN_BIEN_PROXY: PublicStage.KIEM_TRA,
    Stage.SUA_BEAT: PublicStage.KIEM_TRA,
    Stage.CAN_CON_NGUOI_XU_LY: PublicStage.KIEM_TRA,
    Stage.HOAN_THANH: PublicStage.KIEM_TRA,
    Stage.CHO_NGUOI_DUNG_DUYET_PROXY: PublicStage.CHO_NGUOI_DUNG_DUYET_PROXY,
}


def public_stage(stage: Stage) -> PublicStage:
    return _PUBLIC_STAGE_BY_INTERNAL[stage]
