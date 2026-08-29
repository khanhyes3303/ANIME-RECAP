from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
)

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


def test_chrome_launch_detach_keeps_browser_process_alive(tmp_path: Path) -> None:
    class Driver:
        def __init__(self) -> None:
            self.quit_calls = 0

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

    assert driver.quit_calls == 1
    assert process.terminated is False

    launch.close()
    assert driver.quit_calls == 1
    assert process.terminated is True


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


def test_session_passes_bound_account_to_manual_readiness(tmp_path: Path) -> None:
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

    assert "ready:bound" in page.events


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


def test_send_prompt_uses_dom_click_when_send_button_is_intercepted() -> None:
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

    class SendButton(Textbox):
        def click(self) -> None:
            raise ElementClickInterceptedException("microphone wrapper overlaps button")

    class Driver:
        def __init__(self) -> None:
            self.dom_clicked = False

        def find_element(self, kind: str, selector: str):
            if "contenteditable" in selector:
                return Textbox()
            if "Gửi" in selector:
                return SendButton()
            raise NoSuchElementException(f"missing element: {kind} {selector}")

        def execute_script(self, script: str, element: SendButton) -> None:
            assert "click" in script
            self.dom_clicked = True

    driver = Driver()

    SeleniumGeminiPage(driver).send_prompt("GEMINI_WEB_OPERATOR_OK")

    assert driver.dom_clicked is True


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
    )

    assert page.wait_for_response() == "GEMINI_WEB_OPERATOR_OK"


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
    assert [event for event in page.events if event in {"new", "ready"}] == [
        "new",
        "ready",
        "ready",
    ]
    assert "resume:https://gemini.google.com/app/chat-123" in page.events
    assert second.observation.conversation_url == first.observation.conversation_url
    assert first.turns[0].prompt_sha256
