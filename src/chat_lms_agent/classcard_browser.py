from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from chat_lms_agent.classcard_login import ClasscardCredentials, load_classcard_credentials
from chat_lms_agent.classcard_plan import UploadPart, UploadPlan

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


class ClasscardAutomationError(RuntimeError):
    pass


class ClasscardLoginRequired(ClasscardAutomationError):
    pass


class ClasscardPage(Protocol):
    def open_main(self) -> None: ...

    def ensure_logged_in(self) -> None: ...

    def create_set_from_tsv(self, title: str, tsv: str) -> None: ...

    def add_current_set_to_class(self, class_name: str) -> None: ...


@dataclass(frozen=True, slots=True)
class ClasscardBrowserOptions:
    profile_dir: Path | None = None
    headed: bool = False
    slow_mo_ms: int = 0
    credentials: ClasscardCredentials | None = None


@dataclass(frozen=True, slots=True)
class ClasscardSequenceResult:
    checkpoint_path: Path
    completed_indexes: tuple[int, ...]
    status: str


def run_classcard_upload_sequence(
    plan: UploadPlan,
    page: ClasscardPage,
    checkpoint_path: str | Path,
    *,
    start_index: int = 0,
) -> ClasscardSequenceResult:
    checkpoint = Path(checkpoint_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    completed = list(range(start_index))
    page.open_main()
    page.ensure_logged_in()
    for part in plan.parts[start_index:]:
        _write_checkpoint(checkpoint, plan, "uploading", tuple(completed), current_part=part)
        page.create_set_from_tsv(part.title, part.tsv)
        page.add_current_set_to_class(plan.target_class_name)
        completed.append(part.index)
        _write_checkpoint(checkpoint, plan, "part_completed", tuple(completed), current_part=part)
    _write_checkpoint(checkpoint, plan, "completed", tuple(completed), current_part=None)
    return ClasscardSequenceResult(checkpoint, tuple(completed), "completed")


def resume_start_index(checkpoint_path: str | Path) -> int:
    checkpoint = Path(checkpoint_path)
    if not checkpoint.exists():
        return 0
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    completed = payload.get("completed_indexes")
    if not isinstance(completed, list) or not completed:
        return 0
    indexes = {int(index) for index in completed}
    return next(index for index in range(len(indexes) + 1) if index not in indexes)


def upload_plan_with_playwright(
    plan: UploadPlan,
    checkpoint_path: str | Path,
    *,
    options: ClasscardBrowserOptions | None = None,
    start_index: int = 0,
) -> ClasscardSequenceResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ClasscardAutomationError("Playwright is required: py -3 -m pip install playwright && py -3 -m playwright install chromium") from exc
    selected = options or ClasscardBrowserOptions()
    profile_dir = selected.profile_dir or Path.home() / ".chat_lms_agent" / "classcard-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as runtime:
        context = runtime.chromium.launch_persistent_context(
            str(profile_dir),
            headless=not selected.headed,
            slow_mo=selected.slow_mo_ms,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(10_000)
        adapter = PlaywrightClasscardPage(page, selected.credentials or load_classcard_credentials())
        try:
            return run_classcard_upload_sequence(plan, adapter, checkpoint_path, start_index=start_index)
        finally:
            context.close()


class PlaywrightClasscardPage:
    def __init__(self, page: Page, credentials: ClasscardCredentials | None = None) -> None:
        self._page = page
        self._credentials = credentials

    def open_main(self) -> None:
        self._page.goto("https://www.classcard.net/Main", wait_until="domcontentloaded")

    def ensure_logged_in(self) -> None:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        if "/Login" not in self._page.url:
            return
        if self._credentials is not None:
            self._login_with_credentials(self._credentials)
            return
        try:
            self._page.wait_for_url(lambda url: "/Login" not in url, timeout=180_000, wait_until="domcontentloaded")
        except PlaywrightTimeoutError as exc:
            raise ClasscardLoginRequired("Classcard login is required in the opened browser profile") from exc

    def _login_with_credentials(self, credentials: ClasscardCredentials) -> None:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        if not _fill_if_visible(self._page.get_by_placeholder("아이디", exact=False), credentials.username):
            if not _fill_if_visible(self._page.locator("input[type='text']"), credentials.username):
                raise ClasscardAutomationError("Classcard username input was not found")
        if not _fill_if_visible(self._page.get_by_placeholder("비밀번호", exact=False), credentials.password):
            if not _fill_if_visible(self._page.locator("input[type='password']"), credentials.password):
                raise ClasscardAutomationError("Classcard password input was not found")
        self._click_text(("로그인",))
        try:
            self._page.wait_for_url(lambda url: "/Login" not in url, timeout=30_000, wait_until="domcontentloaded")
        except PlaywrightTimeoutError as exc:
            raise ClasscardLoginRequired("Classcard credential login did not complete") from exc

    def create_set_from_tsv(self, title: str, tsv: str) -> None:
        self._click_text(("세트만들기", "세트 만들기", "+ 세트", "새 세트"))
        self._page.wait_for_timeout(1_000)
        self._click_text(("단어 세트",))
        self._page.wait_for_url(lambda url: "CreateWord" in url, timeout=30_000, wait_until="domcontentloaded")
        self._fill_create_word_settings(title)
        rows = _parse_tsv(tsv)
        self._ensure_card_rows(len(rows))
        front_inputs = self._page.locator("textarea[name='front[]']")
        back_inputs = self._page.locator("textarea[name='back[]']")
        for index, (front, back) in enumerate(rows):
            front_inputs.nth(index).fill(front)
            back_inputs.nth(index).fill(back)
        self._click_text(("세트 저장하기",))
        self._page.wait_for_timeout(2_000)

    def add_current_set_to_class(self, class_name: str) -> None:
        self._click_text(("클래스에 추가", "클래스 추가", "과제로 내기", "클래스 담기"))
        self._fill_optional_search(class_name)
        self._click_text((class_name,))
        self._click_text(("추가", "저장", "완료", "확인"))

    def _click_text(self, texts: tuple[str, ...]) -> None:
        for text in texts:
            action = self._page.locator("button, a, [role=button]").filter(has_text=text)
            if _click_if_visible(action):
                return
            button = self._page.get_by_role("button", name=text, exact=False)
            if _click_if_visible(button):
                return
            locator = self._page.get_by_text(text, exact=False)
            if _click_if_visible(locator):
                return
        raise ClasscardAutomationError(f"Classcard control not found: {' / '.join(texts)}")

    def _fill_title(self, title: str) -> None:
        if _fill_if_visible(self._page.get_by_placeholder("세트 제목", exact=False), title):
            return
        if _fill_if_visible(self._page.get_by_placeholder("제목", exact=False), title):
            return
        if _fill_if_visible(self._page.locator("input[name*='title' i]"), title):
            return
        if _fill_if_visible(self._page.locator("input[name='content_title']"), title):
            return
        if _fill_if_visible(self._page.locator("input[name='new_title']"), title):
            return
        if _fill_if_visible(self._page.locator("input[placeholder*='제목']"), title):
            return
        if _fill_if_visible(self._page.locator("input[placeholder*='세트']"), title):
            return
        if _fill_if_visible(self._page.locator("input[placeholder*='콘텐츠']"), title):
            return
        raise ClasscardAutomationError("Classcard set title input was not found")

    def _fill_create_word_settings(self, title: str) -> None:
        setting_modal = self._page.locator("#settingAuth").filter(visible=True)
        if setting_modal.count() > 0:
            if not _fill_if_visible(self._page.locator("#modal_name"), title):
                raise ClasscardAutomationError("Classcard word-set title input was not found")
            direct_input = self._page.locator("#settingAuth a.btn-auth-save").filter(visible=True)
            if direct_input.count() < 1:
                raise ClasscardAutomationError("Classcard direct-input start button was not found")
            direct_input.first.click()
            self._page.wait_for_timeout(1_000)
            return
        self._fill_title(title)

    def _ensure_card_rows(self, count: int) -> None:
        front_inputs = self._page.locator("textarea[name='front[]']")
        while front_inputs.count() < count:
            before = front_inputs.count()
            self._click_text(("카드 추가",))
            self._page.wait_for_timeout(300)
            after = front_inputs.count()
            if after <= before:
                raise ClasscardAutomationError("Classcard card row was not added")

    def _fill_optional_search(self, text: str) -> None:
        _fill_if_visible(self._page.get_by_placeholder("클래스", exact=False), text)
        _fill_if_visible(self._page.get_by_placeholder("검색", exact=False), text)


def _click_if_visible(locator: Locator) -> bool:
    visible = locator.filter(visible=True)
    count = visible.count()
    if count < 1:
        return False
    visible.first.click()
    return True


def _fill_if_visible(locator: Locator, value: str) -> bool:
    visible = locator.filter(visible=True)
    count = visible.count()
    if count < 1:
        return False
    visible.first.fill(value)
    return True


def _parse_tsv(tsv: str) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for line in tsv.splitlines():
        if not line.strip():
            continue
        front, separator, back = line.partition("\t")
        if not separator:
            raise ClasscardAutomationError("Classcard TSV row must contain a tab between word and meaning")
        rows.append((front.strip(), back.strip()))
    return tuple(rows)


def _write_checkpoint(
    checkpoint: Path,
    plan: UploadPlan,
    status: str,
    completed_indexes: tuple[int, ...],
    *,
    current_part: UploadPart | None,
) -> None:
    payload = _existing_checkpoint(checkpoint)
    payload.update({
        "status": status,
        "student": plan.student_name,
        "target_class_name": plan.target_class_name,
        "lesson_date": plan.lesson_date,
        "mode": plan.mode.value,
        "completed_indexes": list(completed_indexes),
        "current_part": current_part.index if current_part else None,
        "parts": [
            {
                "index": part.index,
                "label": part.label,
                "title": part.title,
                "assigned_date": part.assigned_date,
                "word_count": len(part.words),
            }
            for part in plan.parts
        ],
    })
    checkpoint.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _existing_checkpoint(checkpoint: Path) -> dict[str, str | int | list[str] | list[int] | None]:
    if not checkpoint.exists():
        return {}
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items()}
