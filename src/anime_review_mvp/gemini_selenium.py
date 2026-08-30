from __future__ import annotations

import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.ui import WebDriverWait

from .errors import MvpError
from .gemini_operator import BrowserObservation, OperatorPolicy
from .gemini_session import BrowserTurn, GeminiSessionMetadata
from .gemini_web import account_sha256

GEMINI_URL = "https://gemini.google.com/app"

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

# Only target explicit Google account controls. A generic "account" selector
# can match user content such as a Notebook title and navigate away from chat.
ACCOUNT_SELECTORS = (
    (By.CSS_SELECTOR, "button[aria-label*='Google Account' i]"),
    (By.CSS_SELECTOR, "a[aria-label*='Google Account' i]"),
    (By.CSS_SELECTOR, "button[aria-label*='Tài khoản Google' i]"),
    (By.CSS_SELECTOR, "a[aria-label*='Tài khoản Google' i]"),
    (By.CSS_SELECTOR, "[data-email]"),
)
SEND_SELECTORS = (
    (By.CSS_SELECTOR, "button[data-test-id='send-button']"),
    (By.CSS_SELECTOR, "button[aria-label*='Gửi']"),
    (By.CSS_SELECTOR, "button[aria-label*='Send' i]"),
)
UPLOAD_BUSY_SELECTORS = (
    (By.CSS_SELECTOR, "[role='progressbar']"),
    (By.CSS_SELECTOR, "[aria-label*='Đang tải']"),
    (By.CSS_SELECTOR, "[aria-label*='Uploading' i]"),
    (By.CSS_SELECTOR, "[data-test-id*='upload-progress']"),
)
STOP_SELECTORS = (
    (By.CSS_SELECTOR, "button[aria-label*='Dừng']"),
    (By.CSS_SELECTOR, "button[aria-label*='Stop' i]"),
)

USER_SELECTED_LABEL = "USER_SELECTED_NOT_VERIFIED"


class GeminiBrowserError(MvpError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AccountObservation:
    account_sha256: str
    account_hint: str
    plan_label: str


@dataclass(frozen=True, slots=True)
class BrowserReadiness:
    account: AccountObservation
    model_label: str
    mode_label: str


@dataclass(frozen=True, slots=True)
class BrowserConversationResult:
    observation: BrowserObservation
    response: str
    turns: tuple[BrowserTurn, ...]

    def __iter__(self):
        """Keep tuple-unpacking compatibility for existing callers."""
        yield self.observation
        yield self.response


class GeminiPage(Protocol):
    def show(self) -> None: ...

    def open_new_chat(self) -> None: ...

    def verify_account(
        self,
        *,
        expected_account_sha256: str | None = None,
        account_hint: str | None = None,
    ) -> AccountObservation: ...

    def wait_until_ready(
        self,
        policy: OperatorPolicy,
        *,
        expected_account_sha256: str | None = None,
        account_hint: str | None = None,
    ) -> BrowserReadiness: ...

    def open_conversation(self, url: str) -> None: ...

    def select_model(self, label: str) -> str: ...

    def select_mode(self, label: str) -> str: ...

    def upload(self, paths: tuple[Path, ...]) -> None: ...

    def wait_for_uploads_ready(self, paths: tuple[Path, ...]) -> None: ...

    def send_prompt(self, prompt: str) -> None: ...

    def wait_for_response(self) -> str: ...

    def read_conversation_url(self) -> str: ...

    def save_screenshot(self, path: Path) -> None: ...


class ManagedProfileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._descriptor: int | None = None

    def acquire(self) -> None:
        if self._descriptor is not None:
            raise MvpError("Gemini browser session is already active")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise MvpError("Gemini browser session is already active") from exc
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        self._descriptor = descriptor

    def release(self) -> None:
        if self._descriptor is None:
            return
        os.close(self._descriptor)
        self._descriptor = None
        with suppress(FileNotFoundError):
            self.path.unlink()

    def __enter__(self) -> ManagedProfileLock:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def build_chrome_command(
    chrome_path: Path,
    profile_dir: Path,
    debugger_port: int,
) -> list[str]:
    if debugger_port <= 0:
        raise MvpError("Chrome debugger port must be positive")
    return [
        str(chrome_path),
        f"--remote-debugging-port={debugger_port}",
        f"--user-data-dir={profile_dir}",
        "--new-window",
        GEMINI_URL,
    ]


def locate_chrome() -> Path:
    discovered = shutil.which("chrome.exe") or shutil.which("chrome")
    candidates = (
        Path(discovered) if discovered else None,
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise MvpError("Google Chrome is not installed")


def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


@dataclass(slots=True)
class ChromeLaunch:
    page: SeleniumGeminiPage
    process: subprocess.Popen[bytes] | None
    chrome_pid: int
    debugger_address: str
    profile_lock: ManagedProfileLock | None = None
    _driver_closed: bool = field(default=False, init=False, repr=False)

    def detach(self) -> None:
        if not self._driver_closed:
            # DELETE /session closes every attached Chrome window. Stopping only
            # ChromeDriver releases automation while preserving the user's
            # visible Gemini window and its signed-in profile.
            self.page.driver.service.stop()
            self._driver_closed = True
        if self.profile_lock is not None:
            self.profile_lock.release()

    def close(self) -> None:
        try:
            if not self._driver_closed:
                self.page.driver.quit()
                self._driver_closed = True
            if self.profile_lock is not None:
                self.profile_lock.release()
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()


def launch_managed_chrome(
    project_root: Path,
    *,
    chrome_path: Path | None = None,
    timeout_seconds: float = 30.0,
) -> ChromeLaunch:
    local_dir = project_root.resolve() / ".local"
    profile_lock = ManagedProfileLock(local_dir / "gemini_operator.lock")
    profile_lock.acquire()
    process: subprocess.Popen[bytes] | None = None
    try:
        port = _reserve_local_port()
        address = f"127.0.0.1:{port}"
        command = build_chrome_command(
            chrome_path or locate_chrome(),
            local_dir / "gemini_ultra_chrome",
            port,
        )
        process = subprocess.Popen(command)
        deadline = time.monotonic() + timeout_seconds
        version_url = f"http://{address}/json/version"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise GeminiBrowserError("BROWSER_START_FAILED", "Chrome exited during startup")
            try:
                with urllib.request.urlopen(version_url, timeout=1):
                    break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)
        else:
            raise GeminiBrowserError("BROWSER_START_FAILED", "Chrome debugger did not start")
        options = Options()
        options.debugger_address = address
        driver = webdriver.Chrome(options=options)
        return ChromeLaunch(
            SeleniumGeminiPage(driver),
            process,
            process.pid,
            address,
            profile_lock,
        )
    except Exception:
        if process is not None and process.poll() is None:
            process.terminate()
        profile_lock.release()
        raise


def connect_managed_chrome(metadata: GeminiSessionMetadata) -> ChromeLaunch:
    """Attach Selenium to an existing visible Chrome owned by the registry."""
    options = Options()
    options.debugger_address = metadata.debugger_address
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as exc:
        raise GeminiBrowserError(
            "BROWSER_START_FAILED", "Could not attach to managed Gemini Chrome"
        ) from exc
    return ChromeLaunch(
        SeleniumGeminiPage(driver),
        None,
        metadata.chrome_pid,
        metadata.debugger_address,
    )


def _windows_visible_window_handle(pid: int) -> int | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    handles: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def collect(hwnd: int, _lparam: int) -> bool:
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid and user32.IsWindowVisible(hwnd):
            handles.append(int(hwnd))
        return True

    user32.EnumWindows(collect, 0)
    return handles[-1] if handles else None


def _restore_windows_window(handle: int) -> None:
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindowAsync(handle, 9)  # SW_RESTORE
    user32.BringWindowToTop(handle)
    user32.SetForegroundWindow(handle)


def ensure_managed_chrome_visible(
    project_root: Path,
    metadata: GeminiSessionMetadata,
    *,
    chrome_path: Path | None = None,
    timeout_seconds: float = 10.0,
    find_window: Callable[[int], int | None] = _windows_visible_window_handle,
    spawn: Callable[[list[str]], object] = subprocess.Popen,
    restore_window: Callable[[int], None] = _restore_windows_window,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Restore the real operator HWND, reopening it when Chrome is background-only."""
    handle = find_window(metadata.chrome_pid)
    if handle is None:
        try:
            port = int(metadata.debugger_address.rsplit(":", 1)[1])
        except (IndexError, ValueError) as exc:
            raise GeminiBrowserError(
                "BROWSER_START_FAILED", "Gemini debugger address is invalid"
            ) from exc
        command = build_chrome_command(
            chrome_path or locate_chrome(),
            project_root.resolve() / ".local" / "gemini_ultra_chrome",
            port,
        )
        spawn(command)

    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while handle is None and time.monotonic() <= deadline:
        handle = find_window(metadata.chrome_pid)
        if handle is None:
            sleep(0.1)
    if handle is None:
        raise GeminiBrowserError(
            "BROWSER_START_FAILED",
            "Chrome operator is running in background but has no visible Windows window",
        )
    restore_window(handle)
    return handle


def _masked_email(email: str) -> str:
    local, domain = email.casefold().split("@", 1)
    return f"{local[:1]}***@{domain}"


def _is_gemini_chat_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "gemini.google.com"
        and (parsed.path.rstrip("/") == "/app" or parsed.path.startswith("/app/"))
    )


class SeleniumGeminiPage:
    def __init__(
        self,
        driver: WebDriver,
        *,
        timeout_seconds: float = 30.0,
        account_wait_seconds: float = 180.0,
        upload_wait_seconds: float = 300.0,
        response_wait_seconds: float = 900.0,
        response_stable_seconds: float = 2.0,
    ) -> None:
        self.driver = driver
        self._wait = WebDriverWait(driver, timeout_seconds)
        self._account_wait_seconds = max(0.0, account_wait_seconds)
        self._upload_wait_seconds = max(0.0, upload_wait_seconds)
        self._response_wait_seconds = max(0.0, response_wait_seconds)
        self._response_stable_seconds = max(0.0, response_stable_seconds)
        self._response_baseline: tuple[str, ...] | None = None

    def show(self) -> None:
        handles = self.driver.window_handles
        if not handles:
            raise GeminiBrowserError(
                "BROWSER_START_FAILED", "Gemini Chrome has no visible window"
            )
        self.driver.switch_to.window(handles[-1])
        self.driver.maximize_window()
        self.driver.execute_script("window.focus();")

    def confirm_user_ready(self) -> None:
        wait_for_user_ready()

    def _click_first(self, selectors: tuple[tuple[str, str], ...], code: str) -> object:
        for selector in selectors:
            try:
                element = WebDriverWait(self.driver, 3).until(
                    expected.element_to_be_clickable(selector)
                )
                try:
                    element.click()
                except ElementClickInterceptedException:
                    # Gemini's persistent microphone wrapper can overlap the
                    # visual centre of the send button. Dispatch the same DOM
                    # click only after Selenium proves the target is enabled.
                    self.driver.execute_script("arguments[0].click();", element)
                return element
            except (StaleElementReferenceException, TimeoutException):
                continue
        raise GeminiBrowserError(code, f"Gemini element was not found: {code}")

    def _visible_first(self, selectors: tuple[tuple[str, str], ...], code: str) -> object:
        for selector in selectors:
            try:
                return WebDriverWait(self.driver, 3).until(
                    expected.visibility_of_element_located(selector)
                )
            except (StaleElementReferenceException, TimeoutException):
                continue
        raise GeminiBrowserError(code, f"Gemini element was not found: {code}")

    def _try_click_first(
        self,
        selectors: tuple[tuple[str, str], ...],
        *,
        timeout_seconds: float = 0.75,
    ) -> object | None:
        """Click the first currently available selector without blocking a poll."""
        for selector in selectors:
            try:
                element = WebDriverWait(self.driver, timeout_seconds).until(
                    expected.element_to_be_clickable(selector)
                )
                element.click()
                return element
            except TimeoutException:
                continue
        return None

    def open_new_chat(self) -> None:
        self.driver.get(GEMINI_URL)
        try:
            self._wait.until(lambda driver: _is_gemini_chat_url(driver.current_url))
        except TimeoutException as exc:
            raise GeminiBrowserError(
                "WRONG_GEMINI_SURFACE",
                "Gemini normal chat /app is required; Notebook is not supported",
            ) from exc

    def open_conversation(self, url: str) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "gemini.google.com"
            or not parsed.path.startswith("/app/")
            or parsed.path.rstrip("/") == "/app"
        ):
            raise GeminiBrowserError("INVALID_EVIDENCE", "Gemini conversation URL is invalid")
        current = urlparse(str(self.driver.current_url))
        if (
            current.scheme == parsed.scheme
            and current.netloc == parsed.netloc
            and current.path.rstrip("/") == parsed.path.rstrip("/")
        ):
            return
        self.driver.get(url)
        self._wait.until(lambda driver: driver.current_url.startswith(url))

    def verify_account(
        self,
        *,
        expected_account_sha256: str | None = None,
        account_hint: str | None = None,
    ) -> AccountObservation:
        if not _is_gemini_chat_url(str(self.driver.current_url)):
            raise GeminiBrowserError(
                "WRONG_GEMINI_SURFACE",
                "Gemini normal chat /app is required; Notebook is not supported",
            )
        # A managed Chrome profile may need a one-time interactive login. Keep
        # that window alive while polling instead of failing after three
        # seconds and closing it before the user can act.
        deadline = time.monotonic() + self._account_wait_seconds
        account_element: object | None = None
        bound_profile = (
            expected_account_sha256 is not None and account_hint is not None
        )
        last_error = "Signed-in Google email and Ultra plan are not visible"
        while True:
            if account_element is None and not bound_profile:
                account_element = self._try_click_first(ACCOUNT_SELECTORS)
            try:
                body = WebDriverWait(self.driver, 1).until(
                    expected.visibility_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                body = None

            if body is not None:
                try:
                    details: list[str] = [str(getattr(body, "text", ""))]
                    if account_element is not None:
                        details.extend(
                            str(getattr(account_element, attribute, ""))
                            for attribute in ("text",)
                        )
                        get_attribute = getattr(account_element, "get_attribute", None)
                        if callable(get_attribute):
                            details.extend(
                                str(get_attribute(attribute) or "")
                                for attribute in ("aria-label", "data-email", "title")
                            )
                except StaleElementReferenceException:
                    # Gemini frequently replaces the account control while its
                    # menu opens. Drop the old reference and let the next poll
                    # locate the current DOM node.
                    account_element = None
                    continue
                text = "\n".join(details)
                match = re.search(
                    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE
                )
                plan = next(
                    (line.strip() for line in text.splitlines() if "ultra" in line.casefold()),
                    "",
                )
                if match is not None and plan:
                    email = match.group(0)
                    return AccountObservation(
                        account_sha256(email), _masked_email(email), plan
                    )
                if (
                    plan
                    and bound_profile
                ):
                    # Enrollment is the one-time human confirmation for this
                    # dedicated Chrome profile. Chrome's account menu is
                    # outside the web-page DOM, so later sessions prove the
                    # bound profile by its visible Gemini account control and
                    # Ultra plan instead of fabricating an email observation.
                    return AccountObservation(
                        expected_account_sha256,
                        account_hint,
                        plan,
                    )
                if match is not None or (
                    bound_profile
                ):
                    last_error = "Google AI Ultra plan is not visible"
                elif account_element is not None:
                    last_error = "Signed-in Google email is not visible"

            if time.monotonic() >= deadline:
                code = "ACCOUNT_MISMATCH" if "Ultra" in last_error else "LOGIN_REQUIRED"
                raise GeminiBrowserError(code, last_error)
            time.sleep(0.25)

    def _visible_dom_text(self) -> str:
        values: list[str] = []
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            values.append(str(getattr(body, "text", "")))
        except (NoSuchElementException, TimeoutException):
            pass
        selectors = (
            (By.CSS_SELECTOR, "button"),
            (By.CSS_SELECTOR, "[role='button']"),
            (By.CSS_SELECTOR, "[role='menuitem']"),
            (By.CSS_SELECTOR, "[role='option']"),
            (By.CSS_SELECTOR, "[aria-selected='true']"),
            (By.CSS_SELECTOR, "[aria-checked='true']"),
        )
        for kind, selector in selectors:
            for element in self.driver.find_elements(kind, selector):
                try:
                    if not element.is_displayed():
                        continue
                except AttributeError:
                    pass
                values.append(str(getattr(element, "text", "")))
                get_attribute = getattr(element, "get_attribute", None)
                if callable(get_attribute):
                    values.extend(
                        str(get_attribute(attribute) or "")
                        for attribute in ("aria-label", "title")
                    )
        return "\n".join(values)

    def wait_until_ready(
        self,
        policy: OperatorPolicy,
        *,
        expected_account_sha256: str | None = None,
        account_hint: str | None = None,
    ) -> BrowserReadiness:
        account = self.verify_account(
            expected_account_sha256=expected_account_sha256,
            account_hint=account_hint,
        )
        deadline = time.monotonic() + self._account_wait_seconds
        expected_model = policy.model_label.casefold()
        expected_mode = policy.mode_label.casefold()
        last_text = ""
        while True:
            last_text = self._visible_dom_text()
            folded = last_text.casefold()
            if expected_model in folded and expected_mode in folded:
                return BrowserReadiness(account, policy.model_label, policy.mode_label)
            if time.monotonic() >= deadline:
                if expected_model not in folded:
                    raise GeminiBrowserError(
                        "MODEL_NOT_FOUND",
                        f"Gemini model is not {policy.model_label}; "
                        f"observed DOM: {last_text[:240]}",
                    )
                raise GeminiBrowserError(
                    "MODEL_NOT_FOUND",
                    f"Gemini mode is not {policy.mode_label}; observed DOM: {last_text[:240]}",
                )
            time.sleep(0.25)

    def _open_model_menu(self) -> None:
        selectors = (
            (By.CSS_SELECTOR, "button[aria-haspopup='menu']"),
            (By.XPATH, "//button[contains(@aria-label,'mô hình')]"),
            (By.XPATH, "//button[contains(.,'Flash') or contains(.,'Pro')]"),
        )
        self._click_first(selectors, "MODEL_NOT_FOUND")

    def select_model(self, label: str) -> str:
        self._open_model_menu()
        selectors = tuple(
            (kind, value.replace("3.7 Flash", label)) for kind, value in MODEL_SELECTORS
        )
        element = self._click_first(selectors, "MODEL_NOT_FOUND")
        visible = str(getattr(element, "text", "")).strip()
        if label not in visible:
            raise GeminiBrowserError("MODEL_NOT_FOUND", f"Gemini model is not {label}")
        return label

    def select_mode(self, label: str) -> str:
        self._open_model_menu()
        selectors = tuple(
            (kind, value.replace("Tư duy mở rộng", label)) for kind, value in MODE_SELECTORS
        )
        element = self._click_first(selectors, "MODEL_NOT_FOUND")
        visible = str(getattr(element, "text", "")).strip()
        if label not in visible:
            raise GeminiBrowserError("MODEL_NOT_FOUND", f"Gemini mode is not {label}")
        return label

    def upload(self, paths: tuple[Path, ...]) -> None:
        if not paths or any(not path.is_file() for path in paths):
            raise GeminiBrowserError("UPLOAD_FAILED", "Gemini upload files are missing")
        try:
            upload = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")
        except NoSuchElementException:
            self._click_first(
                (
                    (
                        By.CSS_SELECTOR,
                        "button[aria-label*='Nội dung tải lên và công cụ']",
                    ),
                    (
                        By.CSS_SELECTOR,
                        "button[aria-label*='Upload content and tools' i]",
                    ),
                    (By.CSS_SELECTOR, "button[aria-label*='Tải tệp']"),
                    (By.CSS_SELECTOR, "button[aria-label*='Thêm tệp']"),
                    (By.CSS_SELECTOR, "button[aria-label*='Đính kèm']"),
                    (By.CSS_SELECTOR, "button[aria-label*='Add file' i]"),
                    (By.CSS_SELECTOR, "button[aria-label*='Attach' i]"),
                    (By.XPATH, "//button[contains(.,'+')]"),
                ),
                "UPLOAD_FAILED",
            )
            try:
                upload = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            except NoSuchElementException:
                self._click_first(
                    (
                        (
                            By.XPATH,
                            "//*[@role='menuitem' or self::button]"
                            "[contains(.,'Tải tệp lên')]",
                        ),
                        (
                            By.XPATH,
                            "//*[@role='menuitem' or self::button]"
                            "[contains(.,'Tải lên từ thiết bị')]",
                        ),
                        (
                            By.XPATH,
                            "//*[@role='menuitem' or self::button]"
                            "[contains(.,'Upload files') or "
                            "contains(.,'Upload from device')]",
                        ),
                    ),
                    "UPLOAD_FAILED",
                )
                try:
                    upload = WebDriverWait(self.driver, 3).until(
                        expected.presence_of_element_located(
                            (By.CSS_SELECTOR, "input[type='file']")
                        )
                    )
                except TimeoutException as exc:
                    raise GeminiBrowserError(
                        "UPLOAD_FAILED", "Gemini file input is absent"
                    ) from exc
        upload.send_keys("\n".join(str(path.resolve()) for path in paths))

    def wait_for_uploads_ready(self, paths: tuple[Path, ...]) -> None:
        expected_names = tuple(path.name.casefold() for path in paths)

        def uploads_ready(_: WebDriver) -> bool:
            try:
                visible_text = str(
                    getattr(self.driver.find_element(By.TAG_NAME, "body"), "text", "")
                ).casefold()
            except NoSuchElementException:
                return False
            if not all(name in visible_text for name in expected_names):
                return False
            return not any(
                self.driver.find_elements(kind, selector)
                for kind, selector in UPLOAD_BUSY_SELECTORS
            )

        try:
            WebDriverWait(self.driver, self._upload_wait_seconds).until(uploads_ready)
        except TimeoutException as exc:
            raise GeminiBrowserError(
                "UPLOAD_FAILED", "Gemini attachments did not finish uploading"
            ) from exc

    def _response_snapshot(self) -> tuple[str, ...]:
        texts: list[str] = []
        for kind, value in RESPONSE_SELECTORS:
            for element in self.driver.find_elements(kind, value):
                get_attribute = getattr(element, "get_attribute", None)
                raw_text = (
                    get_attribute("textContent")
                    if callable(get_attribute)
                    else getattr(element, "text", "")
                )
                text = str(raw_text or getattr(element, "text", "")).strip()
                if text and text not in texts:
                    texts.append(text)
        return tuple(texts)

    def send_prompt(self, prompt: str) -> None:
        if not prompt.strip():
            raise GeminiBrowserError("INVALID_RESPONSE", "Gemini prompt is empty")
        self._response_baseline = self._response_snapshot()
        textbox = self._visible_first(PROMPT_SELECTORS, "INVALID_RESPONSE")
        textbox.click()
        textbox.send_keys(Keys.CONTROL, "a")
        textbox.send_keys(prompt)
        self._click_first(SEND_SELECTORS, "PROMPT_NOT_SENT")

    def wait_for_response(self) -> str:
        baseline = self._response_baseline
        stable_text = ""
        stable_since = 0.0

        def completed(_: WebDriver) -> str | bool:
            nonlocal stable_since, stable_text
            snapshot = self._response_snapshot()
            is_new_turn = baseline is None or snapshot != baseline
            text = snapshot[-1] if snapshot else ""
            stopping = any(
                self.driver.find_elements(kind, selector)
                for kind, selector in STOP_SELECTORS
            )
            if not text or not is_new_turn or stopping:
                stable_text = ""
                stable_since = 0.0
                return False
            now = time.monotonic()
            if text != stable_text:
                stable_text = text
                stable_since = now
            if now - stable_since < self._response_stable_seconds:
                return False
            return text

        try:
            response = str(
                WebDriverWait(self.driver, self._response_wait_seconds).until(completed)
            )
            self._response_baseline = None
            return response
        except TimeoutException as exc:
            raise GeminiBrowserError(
                "INVALID_RESPONSE", "Gemini response did not complete"
            ) from exc

    def read_conversation_url(self) -> str:
        return self.driver.current_url

    def save_screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self.driver.save_screenshot(str(path)):
            raise GeminiBrowserError("INVALID_EVIDENCE", "Gemini screenshot failed")


def _ask_user_ready_dialog(message: str, timeout_seconds: float) -> bool:
    if sys.platform != "win32":
        return True
    import tkinter as tk

    confirmed = False
    root = tk.Tk()
    root.title("Gemini Web Operator")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    root.geometry("560x190")

    def continue_run() -> None:
        nonlocal confirmed
        confirmed = True
        root.destroy()

    tk.Label(
        root,
        text=message,
        font=("Segoe UI", 13),
        wraplength=500,
        justify="center",
    ).pack(padx=24, pady=(30, 18))
    tk.Button(
        root,
        text="Tiếp tục gửi file + prompt",
        font=("Segoe UI", 11),
        command=continue_run,
        width=28,
    ).pack(pady=8)
    root.protocol("WM_DELETE_WINDOW", continue_run)
    root.after(max(1, int(timeout_seconds * 1_000)), root.destroy)
    root.lift()
    root.focus_force()
    root.mainloop()
    return confirmed


def wait_for_user_ready(
    *,
    ask: Callable[[str, float], bool] = _ask_user_ready_dialog,
    initial_seconds: float = 180,
    reminder_seconds: float = 120,
) -> None:
    if ask("Bạn đã đăng nhập và chọn model xong chưa?", initial_seconds):
        return
    if ask(
        "Gemini vẫn đang chờ. Bấm Tiếp tục để gửi file và prompt.",
        reminder_seconds,
    ):
        return
    raise GeminiBrowserError(
        "USER_CONFIRMATION_TIMEOUT",
        "Không nhận được xác nhận của người dùng sau 5 phút",
    )


def capture_existing_gemini_response(
    page: GeminiPage,
    *,
    conversation_url: str,
    account_hint: str,
    expected_account_sha256: str,
    screenshot_path: Path,
    chrome_pid: int,
    started_at: str,
    clock: Callable[[], str] | None = None,
) -> BrowserConversationResult:
    """Recover an already completed turn without uploading or sending again."""
    show = getattr(page, "show", None)
    if callable(show):
        show()
    page.open_conversation(conversation_url)
    response = page.wait_for_response()
    if not response.strip():
        raise GeminiBrowserError("INVALID_RESPONSE", "Gemini response is empty")
    observed_url = page.read_conversation_url()
    parsed_url = urlparse(observed_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc != "gemini.google.com"
        or not parsed_url.path.startswith("/app/")
    ):
        raise GeminiBrowserError(
            "INVALID_EVIDENCE", "Gemini conversation URL is not a real chat"
        )
    page.save_screenshot(screenshot_path)
    finished_at = (clock or (lambda: datetime.now(UTC).isoformat()))()
    observation = BrowserObservation(
        expected_account_sha256,
        account_hint,
        "USER_SELECTION_NOT_VERIFIED",
        USER_SELECTED_LABEL,
        USER_SELECTED_LABEL,
        observed_url,
        chrome_pid,
        str(screenshot_path.resolve()),
        started_at,
        finished_at,
    )
    return BrowserConversationResult(observation, response, ())


def run_gemini_session(
    page: GeminiPage,
    *,
    policy: OperatorPolicy,
    account_hint: str,
    expected_account_sha256: str,
    upload_paths: tuple[Path, ...],
    prompt: str,
    screenshot_path: Path,
    chrome_pid: int,
    conversation_url: str | None = None,
    clock: Callable[[], str] | None = None,
) -> BrowserConversationResult:
    now = clock or (lambda: datetime.now(UTC).isoformat())
    started_at = now()
    show = getattr(page, "show", None)
    if callable(show):
        show()
    if conversation_url:
        open_conversation = getattr(page, "open_conversation", None)
        if not callable(open_conversation):
            raise GeminiBrowserError("INVALID_EVIDENCE", "Gemini page cannot resume conversation")
        open_conversation(conversation_url)
    else:
        page.open_new_chat()
        confirm_ready = getattr(page, "confirm_user_ready", None)
        if callable(confirm_ready):
            confirm_ready()
    account = AccountObservation(
        expected_account_sha256,
        account_hint,
        "USER_SELECTION_NOT_VERIFIED",
    )
    model_label = USER_SELECTED_LABEL
    mode_label = USER_SELECTED_LABEL
    if upload_paths and any(not path.is_file() for path in upload_paths):
        raise GeminiBrowserError("UPLOAD_FAILED", "Gemini upload files are missing")
    if upload_paths:
        page.upload(upload_paths)
        wait_for_uploads = getattr(page, "wait_for_uploads_ready", None)
        if callable(wait_for_uploads):
            wait_for_uploads(upload_paths)
    page.send_prompt(prompt)
    response = page.wait_for_response()
    if not response.strip():
        raise GeminiBrowserError("INVALID_RESPONSE", "Gemini response is empty")
    conversation_url = page.read_conversation_url()
    parsed_url = urlparse(conversation_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc != "gemini.google.com"
        or not parsed_url.path.startswith("/app/")
    ):
        raise GeminiBrowserError(
            "INVALID_EVIDENCE", "Gemini conversation URL is not a real chat"
        )
    page.save_screenshot(screenshot_path)
    finished_at = now()
    observation = BrowserObservation(
        account.account_sha256,
        account.account_hint,
        account.plan_label,
        model_label,
        mode_label,
        conversation_url,
        chrome_pid,
        str(screenshot_path.resolve()),
        started_at,
        finished_at,
    )
    turn = BrowserTurn(
        1,
        hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        hashlib.sha256(response.encode("utf-8")).hexdigest(),
        conversation_url,
        started_at,
        finished_at,
    )
    return BrowserConversationResult(observation, response, (turn,))
