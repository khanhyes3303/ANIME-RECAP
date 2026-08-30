from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.keys import Keys

import anime_review_mvp.gemini_selenium as gemini_selenium
from anime_review_mvp.errors import MvpError
from anime_review_mvp.gemini_operator import OperatorPolicy
from anime_review_mvp.gemini_selenium import (
    AccountObservation,
    BrowserConversationResult,
    BrowserReadiness,
    BrowserTurn,
    ChromeLaunch,
    GeminiBrowserError,
    ManagedProfileLock,
    SeleniumGeminiPage,
    build_chrome_command,
    run_gemini_session,
)
from anime_review_mvp.gemini_session import GeminiSessionMetadata
from anime_review_mvp.gemini_web import account_sha256


class RecordingPage:
    def __init__(self, screenshot_path: Path) -> None:
        self.events: list[str] = []
        self.screenshot_path = screenshot_path

    def open_new_chat(self) -> None:
        self.events.append("open:new-chat")

    def confirm_user_ready(self) -> None:
        self.events.append("confirm:user-ready")

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

    def wait_for_uploads_ready(self, paths: tuple[Path, ...]) -> None:
        self.events.append(f"upload-ready:{len(paths)}")

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


def test_session_uses_user_confirmation_then_uploads_without_account_model_gate(
    tmp_path: Path,
) -> None:
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
        "confirm:user-ready",
        "upload:2",
        "upload-ready:2",
        "send",
        "wait:complete",
        "read:response",
        "screenshot",
    ]
    assert observation.conversation_url.endswith("real-chat-id")
    assert observation.chrome_pid == 123
    assert response.startswith("{")


def test_user_ready_confirmation_reminds_once_then_continues() -> None:
    calls: list[tuple[str, float]] = []

    def ask(message: str, timeout_seconds: float) -> bool:
        calls.append((message, timeout_seconds))
        return len(calls) == 2

    gemini_selenium.wait_for_user_ready(
        ask=ask,
        initial_seconds=180,
        reminder_seconds=120,
    )

    assert calls == [
        ("Bạn đã đăng nhập và chọn model xong chưa?", 180),
        ("Gemini vẫn đang chờ. Bấm Tiếp tục để gửi file và prompt.", 120),
    ]


def test_capture_existing_response_does_not_upload_or_resend(tmp_path: Path) -> None:
    page = RecordingPage(tmp_path / "session.png")
    page.open_conversation = lambda url: page.events.append(f"resume:{url}")

    result = gemini_selenium.capture_existing_gemini_response(
        page,
        conversation_url="https://gemini.google.com/app/chat-123",
        account_hint="n***@example.com",
        expected_account_sha256="a" * 64,
        screenshot_path=tmp_path / "session.png",
        chrome_pid=123,
        started_at="2026-08-30T02:40:00+07:00",
        clock=lambda: "2026-08-30T02:45:00+07:00",
    )

    assert page.events == [
        "resume:https://gemini.google.com/app/chat-123",
        "wait:complete",
        "read:response",
        "screenshot",
    ]
    assert result.response.startswith("{")
    assert result.observation.model_label == "USER_SELECTED_NOT_VERIFIED"


def test_session_restores_operator_window_before_navigation(tmp_path: Path) -> None:
    class VisiblePage(RecordingPage):
        def show(self) -> None:
            self.events.append("show")

    upload = tmp_path / "manifest.json"
    upload.write_text("{}", encoding="utf-8")
    page = VisiblePage(tmp_path / "session.png")

    _run_page(tmp_path, page, (upload,))

    assert page.events[0] == "show"
    assert page.events[1] == "open:new-chat"


def test_session_does_not_block_on_unverified_account(tmp_path: Path) -> None:
    page = RecordingPage(tmp_path / "session.png")

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

    assert "verify:account" not in page.events
    assert "send" in page.events


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


def test_chrome_launch_detach_keeps_browser_process_alive(tmp_path: Path) -> None:
    class Service:
        def __init__(self) -> None:
            self.stop_calls = 0

        def stop(self) -> None:
            self.stop_calls += 1

    class Driver:
        def __init__(self) -> None:
            self.quit_calls = 0
            self.service = Service()

        def quit(self) -> None:
            self.quit_calls += 1

    class Page:
        def __init__(self, driver: Driver) -> None:
            self.driver = driver

    class Process:
        pid = 123

        def __init__(self) -> None:
            self.terminated = False

        def poll(self) -> None:
            return None if not self.terminated else 0

        def terminate(self) -> None:
            self.terminated = True

    driver = Driver()
    process = Process()
    launch = ChromeLaunch(Page(driver), process, process.pid, "127.0.0.1:9222")

    launch.detach()

    assert driver.quit_calls == 0
    assert driver.service.stop_calls == 1
    assert process.terminated is False

    launch.close()
    assert driver.quit_calls == 0
    assert process.terminated is True


def test_show_restores_latest_operator_window() -> None:
    class SwitchTo:
        def __init__(self) -> None:
            self.selected: str | None = None

        def window(self, handle: str) -> None:
            self.selected = handle

    class Driver:
        window_handles = ["background", "operator"]

        def __init__(self) -> None:
            self.switch_to = SwitchTo()
            self.maximize_calls = 0
            self.focus_calls = 0

        def maximize_window(self) -> None:
            self.maximize_calls += 1

        def execute_script(self, script: str) -> None:
            assert "focus" in script
            self.focus_calls += 1

    driver = Driver()

    SeleniumGeminiPage(driver).show()

    assert driver.switch_to.selected == "operator"
    assert driver.maximize_calls == 1
    assert driver.focus_calls == 1


def test_ensure_managed_chrome_visible_reopens_background_only_operator(
    tmp_path: Path,
) -> None:
    metadata = GeminiSessionMetadata(
        "run-123",
        26300,
        "127.0.0.1:64451",
        None,
        "2026-08-30T12:00:00+00:00",
        {},
    )
    handles = iter((None, None, 9001))
    spawned: list[list[str]] = []
    restored: list[int] = []

    handle = gemini_selenium.ensure_managed_chrome_visible(
        tmp_path,
        metadata,
        chrome_path=Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        timeout_seconds=1,
        find_window=lambda _pid: next(handles),
        spawn=lambda command: spawned.append(command),
        restore_window=lambda value: restored.append(value),
        sleep=lambda _seconds: None,
    )

    assert handle == 9001
    assert spawned == [
        [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "--remote-debugging-port=64451",
            f"--user-data-dir={tmp_path / '.local' / 'gemini_ultra_chrome'}",
            "--new-window",
            "https://gemini.google.com/app",
        ]
    ]
    assert restored == [9001]


def test_session_does_not_block_on_unverified_model(tmp_path: Path) -> None:
    class WrongModelPage(RecordingPage):
        def select_model(self, label: str) -> str:
            self.events.append(f"select:{label}")
            return "Gemini 2.5 Pro Ultra"

    upload = tmp_path / "packet.json"
    upload.write_text("{}", encoding="utf-8")

    page = WrongModelPage(tmp_path / "session.png")

    _run_page(tmp_path, page, (upload,))

    assert not any(event.startswith("select:") for event in page.events)
    assert "send" in page.events


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


def test_account_verification_recovers_when_account_control_is_rerendered() -> None:
    class Element:
        def __init__(self, *, text: str = "", aria: str = "", stale: bool = False) -> None:
            self._text = text
            self.aria = aria
            self.stale = stale

        @property
        def text(self) -> str:
            if self.stale:
                raise StaleElementReferenceException("account control was replaced")
            return self._text

        def click(self) -> None:
            return None

        def is_displayed(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

        def get_attribute(self, name: str) -> str:
            if self.stale:
                raise StaleElementReferenceException("account control was replaced")
            return self.aria if name == "aria-label" else ""

    class Driver:
        current_url = "https://gemini.google.com/app"

        def __init__(self) -> None:
            self.account_calls = 0

        def find_element(self, kind: str, selector: str) -> Element:
            if kind == "css selector" and "account" in selector.casefold():
                self.account_calls += 1
                return Element(aria="Account menu", stale=self.account_calls == 1)
            if selector == "body":
                return Element(text="Signed in: nguyenkhanh@example.com\nGoogle AI Ultra")
            raise AssertionError(f"unexpected selector: {kind} {selector}")

    driver = Driver()
    page = SeleniumGeminiPage(driver, account_wait_seconds=0.2)

    result = page.verify_account()

    assert result.account_sha256 == account_sha256("nguyenkhanh@example.com")
    assert result.plan_label == "Google AI Ultra"
    assert driver.account_calls >= 2


def test_account_verification_accepts_bound_profile_when_ultra_is_visible() -> None:
    class Element:
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
                return Element(text="Khánh Nguyễn\nUltra")
            raise AssertionError(f"unexpected selector: {kind} {selector}")

    result = SeleniumGeminiPage(Driver(), account_wait_seconds=0.0).verify_account(
        expected_account_sha256="a" * 64,
        account_hint="n***@gmail.com",
    )

    assert result == AccountObservation("a" * 64, "n***@gmail.com", "Ultra")


def test_bound_profile_never_clicks_notebook_with_account_in_label() -> None:
    class Element:
        def __init__(self, driver, *, text: str = "") -> None:
            self.driver = driver
            self.text = text

        def click(self) -> None:
            self.driver.notebook_clicked = True
            self.driver.current_url = "https://gemini.google.com/notebook/notebook-id"

        def is_displayed(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

        def get_attribute(self, name: str) -> str:
            if name == "aria-label":
                return "YouTube Authentication and Account Management Gateway"
            return ""

    class Driver:
        current_url = "https://gemini.google.com/app"

        def __init__(self) -> None:
            self.notebook_clicked = False

        def find_element(self, kind: str, selector: str) -> Element:
            if kind == "css selector" and "account" in selector.casefold():
                return Element(self)
            if selector == "body":
                return Element(self, text="Khánh Nguyễn\nUltra")
            raise NoSuchElementException(f"missing element: {kind} {selector}")

    driver = Driver()

    result = SeleniumGeminiPage(driver, account_wait_seconds=0.0).verify_account(
        expected_account_sha256="a" * 64,
        account_hint="n***@gmail.com",
    )

    assert result == AccountObservation("a" * 64, "n***@gmail.com", "Ultra")
    assert driver.notebook_clicked is False
    assert driver.current_url == "https://gemini.google.com/app"


def test_account_verification_rejects_notebook_surface() -> None:
    class Driver:
        current_url = "https://gemini.google.com/notebook/notebook-id"

    page = SeleniumGeminiPage(Driver(), account_wait_seconds=0.0)

    with pytest.raises(GeminiBrowserError) as raised:
        page.verify_account(
            expected_account_sha256="a" * 64,
            account_hint="n***@gmail.com",
        )

    assert raised.value.code == "WRONG_GEMINI_SURFACE"
    assert "/app" in str(raised.value)


def test_account_verification_rejects_bound_profile_without_ultra() -> None:
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
                element.text = "Khánh Nguyễn\nGemini Free"
                return element
            raise AssertionError(f"unexpected selector: {kind} {selector}")

    page = SeleniumGeminiPage(Driver(), account_wait_seconds=0.0)

    with pytest.raises(GeminiBrowserError, match="Ultra"):
        page.verify_account(
            expected_account_sha256="a" * 64,
            account_hint="n***@gmail.com",
        )


def test_session_skips_bound_account_and_model_readiness_gate(tmp_path: Path) -> None:
    class BoundReadyPage(RecordingPage):
        def wait_until_ready(
            self,
            policy: OperatorPolicy,
            *,
            expected_account_sha256: str,
            account_hint: str,
        ) -> BrowserReadiness:
            self.events.append("ready:bound")
            return BrowserReadiness(
                AccountObservation(expected_account_sha256, account_hint, "Ultra"),
                policy.model_label,
                policy.mode_label,
            )

    upload = tmp_path / "packet.json"
    upload.write_text("{}", encoding="utf-8")
    page = BoundReadyPage(tmp_path / "session.png")

    run_gemini_session(
        page,
        policy=OperatorPolicy.required(),
        account_hint="n***@gmail.com",
        expected_account_sha256="a" * 64,
        upload_paths=(upload,),
        prompt="Return JSON only",
        screenshot_path=tmp_path / "session.png",
        chrome_pid=123,
    )

    assert "ready:bound" not in page.events
    assert "send" in page.events


def test_upload_chooses_local_file_after_opening_attachment_menu(
    tmp_path: Path,
) -> None:
    class Element:
        def __init__(self, *, on_click=None, sent: list[str] | None = None) -> None:
            self.on_click = on_click
            self.sent = sent

        def click(self) -> None:
            if self.on_click is not None:
                self.on_click()

        def is_displayed(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

        def send_keys(self, value: str) -> None:
            if self.sent is None:
                raise AssertionError("send_keys called on a non-input element")
            self.sent.append(value)

    class Driver:
        def __init__(self) -> None:
            self.menu_open = False
            self.file_input_ready = False
            self.sent: list[str] = []

        def find_element(self, kind: str, selector: str) -> Element:
            if kind == "css selector" and selector == "input[type='file']":
                if not self.file_input_ready:
                    raise NoSuchElementException("file input is not mounted")
                return Element(sent=self.sent)
            if kind == "css selector" and "Tải tệp" in selector:
                return Element(on_click=lambda: setattr(self, "menu_open", True))
            if kind == "xpath" and "Tải tệp lên" in selector and self.menu_open:
                return Element(
                    on_click=lambda: setattr(self, "file_input_ready", True)
                )
            raise NoSuchElementException(f"missing element: {kind} {selector}")

    source = tmp_path / "operator-smoke.txt"
    source.write_text("smoke", encoding="utf-8")
    driver = Driver()

    SeleniumGeminiPage(driver).upload((source,))

    assert driver.sent == [str(source.resolve())]


def test_upload_opens_current_gemini_upload_tools_menu(tmp_path: Path) -> None:
    class Element:
        def __init__(self, *, on_click=None, sent: list[str] | None = None) -> None:
            self.on_click = on_click
            self.sent = sent

        def click(self) -> None:
            if self.on_click is not None:
                self.on_click()

        def is_displayed(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

        def send_keys(self, value: str) -> None:
            if self.sent is None:
                raise AssertionError("send_keys called on a non-input element")
            self.sent.append(value)

    class Driver:
        def __init__(self) -> None:
            self.menu_open = False
            self.sent: list[str] = []

        def find_element(self, kind: str, selector: str) -> Element:
            if kind == "css selector" and selector == "input[type='file']":
                if not self.menu_open:
                    raise NoSuchElementException("file input is not mounted")
                return Element(sent=self.sent)
            if (
                kind == "css selector"
                and "Nội dung tải lên và công cụ" in selector
            ):
                return Element(on_click=lambda: setattr(self, "menu_open", True))
            raise NoSuchElementException(f"missing element: {kind} {selector}")

    source = tmp_path / "operator-smoke.txt"
    source.write_text("smoke", encoding="utf-8")
    driver = Driver()

    SeleniumGeminiPage(driver).upload((source,))

    assert driver.sent == [str(source.resolve())]


def test_open_conversation_does_not_reload_the_active_chat() -> None:
    class Driver:
        current_url = "https://gemini.google.com/app/chat-123"

        def __init__(self) -> None:
            self.opened: list[str] = []

        def get(self, url: str) -> None:
            self.opened.append(url)

    driver = Driver()

    SeleniumGeminiPage(driver).open_conversation(driver.current_url)

    assert driver.opened == []


def test_upload_waits_until_every_attachment_is_visible_and_not_busy(
    tmp_path: Path,
) -> None:
    first = tmp_path / "manifest.json"
    second = tmp_path / "script_evidence.mp4"
    first.write_text("{}", encoding="utf-8")
    second.write_bytes(b"video")

    class Body:
        def __init__(self, text: str) -> None:
            self.text = text

    class Driver:
        def __init__(self) -> None:
            self.polls = 0

        def find_element(self, kind: str, selector: str) -> Body:
            if selector != "body":
                raise NoSuchElementException(selector)
            self.polls += 1
            if self.polls == 1:
                return Body("manifest.json")
            return Body("manifest.json script_evidence.mp4")

        def find_elements(self, kind: str, selector: str) -> list[object]:
            if self.polls < 2:
                return [object()]
            return []

    driver = Driver()
    page = SeleniumGeminiPage(driver, upload_wait_seconds=1.0)

    page.wait_for_uploads_ready((first, second))

    assert driver.polls >= 2


def test_send_prompt_clicks_send_button_instead_of_pressing_enter() -> None:
    class Textbox:
        text = ""

        def __init__(self) -> None:
            self.sent: list[object] = []

        def click(self) -> None:
            return None

        def is_displayed(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

        def send_keys(self, *values: str) -> None:
            self.sent.extend(values)

    class SendButton:
        def __init__(self) -> None:
            self.clicked = False

        def click(self) -> None:
            self.clicked = True

        def is_displayed(self) -> bool:
            return True

        def is_enabled(self) -> bool:
            return True

    class Driver:
        def __init__(self) -> None:
            self.textbox = Textbox()
            self.send_button = SendButton()

        def find_element(self, kind: str, selector: str):
            if "contenteditable" in selector:
                return self.textbox
            if "send-button" in selector:
                return self.send_button
            raise NoSuchElementException(f"missing element: {kind} {selector}")

        def find_elements(self, kind: str, selector: str):
            return []

    driver = Driver()

    SeleniumGeminiPage(driver).send_prompt("GEMINI_WEB_OPERATOR_OK")

    assert driver.textbox.sent[-1] == "GEMINI_WEB_OPERATOR_OK"
    assert Keys.ENTER not in driver.textbox.sent
    assert driver.send_button.clicked is True


def test_response_wait_does_not_return_the_previous_turn() -> None:
    class Response:
        def __init__(self, text: str) -> None:
            self.text = text

    class Driver:
        def __init__(self) -> None:
            self.response_text = "old response"

        def find_element(self, kind: str, selector: str):
            if "contenteditable" in selector:
                class Textbox:
                    text = ""

                    def click(self) -> None:
                        return None

                    def is_displayed(self) -> bool:
                        return True

                    def is_enabled(self) -> bool:
                        return True

                    def send_keys(self, *values: str) -> None:
                        return None

                return Textbox()
            if "send-button" in selector:
                class SendButton:
                    def click(inner_self) -> None:
                        return None

                    def is_displayed(inner_self) -> bool:
                        return True

                    def is_enabled(inner_self) -> bool:
                        return True

                return SendButton()
            raise NoSuchElementException(selector)

        def find_elements(self, kind: str, selector: str):
            if "response-content" in selector:
                return [Response(self.response_text)]
            return []

    page = SeleniumGeminiPage(
        Driver(), timeout_seconds=0.0, response_wait_seconds=0.0
    )
    page.send_prompt("new prompt")

    with pytest.raises(GeminiBrowserError, match="did not complete"):
        page.wait_for_response()


def test_response_wait_is_independent_from_short_ui_timeout() -> None:
    class Response:
        text = "GEMINI_WEB_OPERATOR_OK"

    class Driver:
        def __init__(self) -> None:
            self.response_checks = 0

        def find_elements(self, kind: str, selector: str):
            if "Dừng" in selector or "Stop" in selector:
                return []
            self.response_checks += 1
            return [Response()] if self.response_checks >= 2 else []

    page = SeleniumGeminiPage(
        Driver(),
        timeout_seconds=0.0,
        response_wait_seconds=1.0,
        response_stable_seconds=0.0,
    )

    assert page.wait_for_response() == "GEMINI_WEB_OPERATOR_OK"


def test_response_uses_dom_text_content_instead_of_visual_line_wrapping() -> None:
    class Response:
        text = '{"note":"line\nwrapped"}'

        def get_attribute(self, name: str) -> str:
            if name == "textContent":
                return '{"note":"line wrapped"}'
            return ""

    class Driver:
        def find_elements(self, kind: str, selector: str):
            if "response-content" in selector:
                return [Response()]
            return []

    page = SeleniumGeminiPage(
        Driver(), response_wait_seconds=1.0, response_stable_seconds=0.0
    )

    assert page.wait_for_response() == '{"note":"line wrapped"}'


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


def test_session_resumes_existing_conversation_and_records_turn(tmp_path: Path) -> None:
    class Page:
        def __init__(self) -> None:
            self.events: list[str] = []

        def open_new_chat(self) -> None:
            self.events.append("new")

        def open_conversation(self, url: str) -> None:
            self.events.append(f"resume:{url}")

        def confirm_user_ready(self) -> None:
            self.events.append("confirm")

        def wait_until_ready(
            self,
            policy: OperatorPolicy,
            *,
            expected_account_sha256: str | None = None,
            account_hint: str | None = None,
        ) -> BrowserReadiness:
            self.events.append("ready")
            assert expected_account_sha256 == account_sha256(
                "nguyenkhanh@example.com"
            )
            assert account_hint == "n***@example.com"
            return BrowserReadiness(
                AccountObservation(
                    account_sha256("nguyenkhanh@example.com"),
                    "n***@example.com",
                    "Google AI Ultra",
                ),
                policy.model_label,
                policy.mode_label,
            )

        def upload(self, paths: tuple[Path, ...]) -> None:
            self.events.append(f"upload:{len(paths)}")

        def send_prompt(self, prompt: str) -> None:
            self.events.append(f"send:{prompt}")

        def wait_for_response(self) -> str:
            self.events.append("wait")
            return '{"phase":"SCRIPT"}'

        def read_conversation_url(self) -> str:
            return "https://gemini.google.com/app/chat-123"

        def save_screenshot(self, path: Path) -> None:
            Image.effect_noise((1280, 720), 64).convert("RGB").save(path)

    upload = tmp_path / "packet.json"
    upload.write_text("{}", encoding="utf-8")
    page = Page()
    first = run_gemini_session(
        page,
        policy=OperatorPolicy.required(),
        account_hint="n***@example.com",
        expected_account_sha256=account_sha256("nguyenkhanh@example.com"),
        upload_paths=(upload,),
        prompt="first",
        screenshot_path=tmp_path / "session-1.png",
        chrome_pid=123,
    )
    second = run_gemini_session(
        page,
        policy=OperatorPolicy.required(),
        account_hint="n***@example.com",
        expected_account_sha256=account_sha256("nguyenkhanh@example.com"),
        upload_paths=(upload,),
        prompt="second",
        screenshot_path=tmp_path / "session-2.png",
        chrome_pid=123,
        conversation_url=first.observation.conversation_url,
    )

    assert isinstance(first, BrowserConversationResult)
    assert isinstance(first.turns[0], BrowserTurn)
    assert [event for event in page.events if event in {"new", "ready"}] == ["new"]
    assert [event for event in page.events if event == "confirm"] == ["confirm"]
    assert "resume:https://gemini.google.com/app/chat-123" in page.events
    assert second.observation.conversation_url == first.observation.conversation_url
    assert first.turns[0].prompt_sha256
