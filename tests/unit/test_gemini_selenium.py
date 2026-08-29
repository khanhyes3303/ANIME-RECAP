from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from anime_review_mvp.errors import MvpError
from anime_review_mvp.gemini_operator import OperatorPolicy
from anime_review_mvp.gemini_selenium import (
    AccountObservation,
    BrowserReadiness,
    GeminiBrowserError,
    ManagedProfileLock,
    SeleniumGeminiPage,
    build_chrome_command,
    run_gemini_session,
)
from anime_review_mvp.gemini_web import account_sha256


class RecordingPage:
    def __init__(self, screenshot_path: Path) -> None:
        self.events: list[str] = []
        self.screenshot_path = screenshot_path

    def open_new_chat(self) -> None:
        self.events.append("open:new-chat")

    def verify_account(self) -> AccountObservation:
        self.events.append("verify:account")
        return AccountObservation(
            account_sha256("nguyenkhanh@example.com"),
            "n***@example.com",
            "Google AI Ultra",
        )

    def select_model(self, label: str) -> str:
        self.events.append(f"select:{label}")
        return label

    def select_mode(self, label: str) -> str:
        self.events.append(f"select:{label}")
        return label

    def upload(self, paths: tuple[Path, ...]) -> None:
        self.events.append(f"upload:{len(paths)}")

    def send_prompt(self, prompt: str) -> None:
        assert prompt == "Return JSON only"
        self.events.append("send")

    def wait_for_response(self) -> str:
        self.events.append("wait:complete")
        return '{"phase":"SCRIPT","overall_verdict":"MATCH"}'

    def read_conversation_url(self) -> str:
        self.events.append("read:response")
        return "https://gemini.google.com/app/real-chat-id"

    def save_screenshot(self, path: Path) -> None:
        self.events.append("screenshot")
        Image.effect_noise((1280, 720), 64).convert("RGB").save(path)


def _run_page(tmp_path: Path, page: RecordingPage, uploads: tuple[Path, ...]) -> None:
    run_gemini_session(
        page,
        policy=OperatorPolicy.required(),
        account_hint="n***@example.com",
        expected_account_sha256=account_sha256("nguyenkhanh@example.com"),
        upload_paths=uploads,
        prompt="Return JSON only",
        screenshot_path=tmp_path / "session.png",
        chrome_pid=123,
    )


def test_session_selects_required_model_mode_uploads_and_reads_real_url(tmp_path: Path) -> None:
    page = RecordingPage(tmp_path / "session.png")
    uploads = (tmp_path / "evidence.mp4", tmp_path / "manifest.json")
    for path in uploads:
        path.write_bytes(b"packet")

    observation, response = run_gemini_session(
        page,
        policy=OperatorPolicy.required(),
        account_hint="n***@example.com",
        expected_account_sha256=account_sha256("nguyenkhanh@example.com"),
        upload_paths=uploads,
        prompt="Return JSON only",
        screenshot_path=tmp_path / "session.png",
        chrome_pid=123,
        clock=iter(
            ("2026-08-29T21:00:00+07:00", "2026-08-29T21:00:10+07:00")
        ).__next__,
    )

    assert page.events == [
        "open:new-chat",
        "verify:account",
        "select:3.7 Flash",
        "select:Tư duy mở rộng",
        "upload:2",
        "send",
        "wait:complete",
        "read:response",
        "screenshot",
    ]
    assert observation.conversation_url.endswith("real-chat-id")
    assert observation.chrome_pid == 123
    assert response.startswith("{")


def test_session_stops_before_model_selection_for_wrong_account(tmp_path: Path) -> None:
    page = RecordingPage(tmp_path / "session.png")

    with pytest.raises(MvpError, match="account"):
        run_gemini_session(
            page,
            policy=OperatorPolicy.required(),
            account_hint="x***@example.com",
            expected_account_sha256="f" * 64,
            upload_paths=(),
            prompt="Return JSON only",
            screenshot_path=tmp_path / "session.png",
            chrome_pid=123,
        )

    assert page.events == ["open:new-chat", "verify:account"]


def test_chrome_command_is_visible_and_uses_dedicated_profile(tmp_path: Path) -> None:
    command = build_chrome_command(
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        tmp_path / "gemini_ultra_chrome",
        9222,
    )

    assert "--headless" not in " ".join(command).casefold()
    assert f"--user-data-dir={tmp_path / 'gemini_ultra_chrome'}" in command
    assert "--remote-debugging-port=9222" in command
    assert command[-1] == "https://gemini.google.com/app"


def test_second_browser_session_cannot_take_same_profile_lock(tmp_path: Path) -> None:
    first = ManagedProfileLock(tmp_path / "gemini_operator.lock")
    second = ManagedProfileLock(tmp_path / "gemini_operator.lock")

    first.acquire()
    try:
        with pytest.raises(MvpError, match="already active"):
            second.acquire()
    finally:
        first.release()


def test_session_rejects_model_label_not_confirmed_by_dom(tmp_path: Path) -> None:
    class WrongModelPage(RecordingPage):
        def select_model(self, label: str) -> str:
            self.events.append(f"select:{label}")
            return "Gemini 2.5 Pro Ultra"

    upload = tmp_path / "packet.json"
    upload.write_text("{}", encoding="utf-8")

    with pytest.raises(MvpError, match="3.7 Flash"):
        _run_page(tmp_path, WrongModelPage(tmp_path / "session.png"), (upload,))


def test_session_rejects_missing_upload_before_sending(tmp_path: Path) -> None:
    page = RecordingPage(tmp_path / "session.png")

    with pytest.raises(MvpError, match="upload"):
        _run_page(tmp_path, page, (tmp_path / "missing.mp4",))

    assert "send" not in page.events


def test_session_rejects_empty_response(tmp_path: Path) -> None:
    class EmptyResponsePage(RecordingPage):
        def wait_for_response(self) -> str:
            self.events.append("wait:complete")
            return ""

    upload = tmp_path / "packet.json"
    upload.write_text("{}", encoding="utf-8")

    with pytest.raises(MvpError, match="response"):
        _run_page(tmp_path, EmptyResponsePage(tmp_path / "session.png"), (upload,))


def test_session_rejects_bare_app_url(tmp_path: Path) -> None:
    class BareUrlPage(RecordingPage):
        def read_conversation_url(self) -> str:
            self.events.append("read:response")
            return "https://gemini.google.com/app"

    upload = tmp_path / "packet.json"
    upload.write_text("{}", encoding="utf-8")

    with pytest.raises(MvpError, match="conversation URL"):
        _run_page(tmp_path, BareUrlPage(tmp_path / "session.png"), (upload,))


def test_account_verification_accepts_generic_account_aria_label() -> None:
    class Element:
        text = ""

        def __init__(self, *, text: str = "", aria: str = "") -> None:
            self.text = text
            self.aria = aria

        def click(self) -> None:
            return None

        def is_displayed(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

        def get_attribute(self, name: str) -> str:
            return self.aria if name == "aria-label" else ""

    class Driver:
        current_url = "https://gemini.google.com/app"

        def find_element(self, kind: str, selector: str) -> Element:
            if kind == "css selector" and "account" in selector.casefold():
                return Element(aria="Account menu")
            if selector == "body":
                return Element(text="Signed in: nguyenkhanh@example.com\nGoogle AI Ultra")
            raise AssertionError(f"unexpected selector: {kind} {selector}")

    page = SeleniumGeminiPage(Driver())

    result = page.verify_account()

    assert result.account_sha256 == account_sha256("nguyenkhanh@example.com")
    assert result.account_hint == "n***@example.com"
    assert result.plan_label == "Google AI Ultra"


def test_wait_until_ready_reads_manual_model_and_mode_without_selecting() -> None:
    class Element:
        def __init__(
            self,
            *,
            text: str = "",
            aria: str = "",
            selected: str = "true",
        ) -> None:
            self.text = text
            self.aria = aria
            self.selected = selected
            self.clicked = False

        def click(self) -> None:
            self.clicked = True

        def is_displayed(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

        def get_attribute(self, name: str) -> str:
            return {
                "aria-label": self.aria,
                "aria-selected": self.selected,
                "aria-checked": self.selected,
            }.get(name, "")

    class Driver:
        current_url = "https://gemini.google.com/app"

        def __init__(self) -> None:
            self.account = Element(aria="Account menu")
            self.model = Element(text="3.7 Flash", aria="3.7 Flash")
            self.mode = Element(text="Tư duy mở rộng", aria="Tư duy mở rộng")
            self.menu_clicks = 0

        def find_element(self, kind: str, selector: str) -> Element:
            if kind == "css selector" and "account" in selector.casefold():
                return self.account
            if selector == "body":
                return Element(
                    text=(
                        "Signed in: nguyenkhanh@example.com\n"
                        "Google AI Ultra\n3.7 Flash\nTư duy mở rộng"
                    )
                )
            raise AssertionError(f"unexpected selector: {kind} {selector}")

        def find_elements(self, kind: str, selector: str) -> list[Element]:
            if kind == "xpath" or kind == "css selector":
                return [self.model, self.mode]
            return []

    driver = Driver()
    result = SeleniumGeminiPage(driver, account_wait_seconds=0.1).wait_until_ready(
        OperatorPolicy.required()
    )

    assert isinstance(result, BrowserReadiness)
    assert result.account.account_sha256 == account_sha256("nguyenkhanh@example.com")
    assert result.model_label == "3.7 Flash"
    assert result.mode_label == "Tư duy mở rộng"
    assert driver.menu_clicks == 0


def test_wait_until_ready_rejects_wrong_manual_model() -> None:
    class Element:
        text = ""

        def click(self) -> None:
            return None

        def is_displayed(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

        def get_attribute(self, name: str) -> str:
            return "Account menu" if name == "aria-label" else ""

    class Driver:
        current_url = "https://gemini.google.com/app"

        def find_element(self, kind: str, selector: str) -> Element:
            if kind == "css selector" and "account" in selector.casefold():
                return Element()
            if selector == "body":
                element = Element()
                element.text = (
                    "Signed in: nguyenkhanh@example.com\nGoogle AI Ultra\n"
                    "2.5 Pro\nTư duy mở rộng"
                )
                return element
            raise AssertionError(f"unexpected selector: {kind} {selector}")

        def find_elements(self, kind: str, selector: str) -> list[Element]:
            return []

    page = SeleniumGeminiPage(Driver(), account_wait_seconds=0.0)
    with pytest.raises(GeminiBrowserError, match="model"):
        page.wait_until_ready(OperatorPolicy.required())
