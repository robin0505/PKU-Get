import sys
import os


if getattr(sys, "frozen", False):
    # 获取打包后的临时目录
    base_path = sys._MEIPASS

    # 1. 添加根目录到 PATH
    os.environ["PATH"] = base_path + os.pathsep + os.environ["PATH"]

    # 2. 添加 pythonnet 可能存在的子目录 (针对不同版本的容错)
    runtime_path = os.path.join(base_path, "pythonnet", "runtime")
    if os.path.exists(runtime_path):
        os.environ["PATH"] = runtime_path + os.pathsep + os.environ["PATH"]

    # 3. 强制 stdout/stderr 使用 UTF-8 编码，防止 Windows 控制台 GBK 编码错误
    import io

    if sys.stdout and isinstance(sys.stdout, io.TextIOWrapper):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if sys.stderr and isinstance(sys.stderr, io.TextIOWrapper):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import io

if sys.stdout:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr:
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import json
import threading
import logging
import re
import webview
import time
from pathlib import Path
from datetime import datetime

# Add current directory to path so we can import pku_downloader
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pku_downloader.config import Config
from pku_downloader.browser import get_driver
from pku_downloader.auth import PKUAuth
from pku_downloader.download import Downloader
from pku_downloader.course_config import ensure_course_config
from pku_downloader.logger import setup_logger, get_logger
from selenium.common.exceptions import WebDriverException

setup_logger(log_file="gui_downloader.log", level=logging.DEBUG)
gui_logger = get_logger("gui")


class WebviewHandler(logging.Handler):
    """把日志转发给前端 JS"""

    def __init__(self):
        super().__init__()
        self.window = None
        self.ready = False

    def set_window(self, window):
        self.window = window
        self.ready = True

    def emit(self, record):
        if not self.ready or not self.window:
            return
        try:
            msg = self.format(record)
            # 这里的 msg 格式取决于 formatter，我们在下面设置
            self.window.evaluate_js(
                f"if(window.addLog) window.addLog({json.dumps(msg)})"
            )
        except Exception:
            pass


root_logger = logging.getLogger()
webview_handler = WebviewHandler()
webview_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")
)
webview_handler.setLevel(logging.DEBUG)
root_logger.addHandler(webview_handler)


class Api:
    def __init__(self):
        self._window = None
        self._config_path = self._get_default_config_path()
        self._state_path = self._config_path.parent / "state.json"
        self.courses = []
        self.session = None
        self.driver = None
        self._pending_config = None  # 🔑 用于延迟保存配置，只在登录成功后保存

    def set_window(self, window):
        self._window = window
        webview_handler.set_window(window)

    def _get_default_config_path(self):
        save_dir = Path.home() / ".pku_downloader"
        save_dir.mkdir(exist_ok=True)
        return save_dir / "config.ini"

    def _load_state(self):
        """Load runtime state (last sync time, etc)"""
        if self._state_path.exists():
            try:
                with open(self._state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {"last_sync": "Never", "total_files": 0, "last_added": 0}

    def _save_state(self, state_update):
        """Update and save runtime state"""
        current = self._load_state()
        current.update(state_update)
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(current, f)
        except Exception as e:
            gui_logger.error(f"Failed to save state: {e}")

    def get_init_state(self):
        """Called by frontend on mount to decide which view to show"""
        config = self.load_config()
        state = self._load_state()

        # Check if we have valid credentials
        has_creds = bool(config["username"] and config["password"])

        # 🔑 如果有凭证，尝试加载已保存的课程列表
        if has_creds:
            self._load_saved_courses()

        # Scan local files for stats
        local_stats = self._scan_local_files(config["download_dir"])

        return {
            "view": "dashboard"
            if (has_creds and len(self.courses) > 0)
            else "login",  # 🔑 修复：需要凭证且有课程数据
            "config": config,
            "state": state,
            "courses": self.courses,  # 🔑 返回课程列表
            "local_stats": local_stats,
            "should_auto_sync": has_creds
            and config.get("auto_sync", False)
            and len(self.courses) > 0,  # 🔑 标记是否需要自动同步
        }

    def _scan_local_files(self, download_dir):
        """Quickly count files in download directory"""
        total_files = 0
        course_stats = {}

        try:
            root_path = Path(download_dir)
            if not root_path.exists():
                return {"total": 0, "courses": {}}

            # Walk through directories
            for entry in os.scandir(root_path):
                if entry.is_dir():
                    count = 0
                    for _, _, files in os.walk(entry.path):
                        count += len(files)
                    course_stats[entry.name] = count
                    total_files += count
        except Exception as e:
            gui_logger.error(f"Scan error: {e}")

        return {"total": total_files, "courses": course_stats}

    def _ensure_default_selected_tabs_for_courses(self):
        """Auto-heal legacy empty selected_tabs.

        Some historical caches have selected_tabs=[], which makes downloader
        skip every course with 'No tabs selected'. For active courses, if
        '教学内容' exists in available_tabs and selected_tabs is empty, we set
        selected_tabs=['教学内容'].
        """
        changed = False

        for course in self.courses:
            if course.get("skip", False):
                continue

            selected_tabs = course.get("selected_tabs")
            available_tabs = course.get("available_tabs") or []

            if isinstance(selected_tabs, list) and len(selected_tabs) == 0:
                if "教学内容" in available_tabs:
                    course["selected_tabs"] = ["教学内容"]
                    changed = True

        return changed

    def load_config(self):
        """Load existing config or return defaults"""
        try:
            if self._config_path.exists():
                cfg = Config(str(self._config_path))
                return {
                    "username": cfg.get("username"),
                    "password": cfg.get("password"),
                    "download_dir": cfg.get("download_dir"),
                    "browser": cfg.get("browser"),
                    "headless": cfg.getbool(
                        "headless", False
                    ),  # Read from config, default to False
                    "concurrent_downloads": cfg.getint("concurrent_downloads", 3),
                    "auto_sync": cfg.getbool(
                        "auto_sync", False
                    ),  # 🔑 添加auto_sync配置
                    "language": cfg.get("language", "en"),  # 🔑 添加语言配置
                }
        except Exception as e:
            gui_logger.error(f"Error loading config: {e}")

        # Get default browser based on platform
        import platform

        system = platform.system()
        if system == "Windows":
            default_browser = "edge"
        elif system == "Darwin":  # macOS
            default_browser = "safari"
        else:  # Linux and others
            default_browser = "chrome"

        return {
            "username": "",
            "password": "",
            "download_dir": str(Path.home() / "Downloads" / "PKU_Courses"),
            "browser": default_browser,
            "headless": False,
            "concurrent_downloads": 3,
            "auto_sync": False,  # 🔑 默认关闭自动同步
            "language": "en",  # 🔑 默认英文
        }

    def save_config(self, data):
        """Save configuration to file"""
        try:
            course_config_path = self._config_path.parent / "courses.json"

            content = Config.TEMPLATE.format(
                username=data["username"],
                password=data["password"],
                download_dir=data["download_dir"].replace("\\", "/"),
                course_config_path=str(course_config_path).replace("\\", "/"),
            )

            import configparser

            parser = configparser.ConfigParser()
            parser.read_string(content)

            if not parser.has_section("Advanced"):
                parser.add_section("Advanced")
            parser.set("Advanced", "browser", data["browser"])
            parser.set("Advanced", "headless", str(data["headless"]).lower())
            parser.set(
                "Advanced", "auto_sync", str(data.get("auto_sync", False)).lower()
            )  # 🔑 保存auto_sync设置
            parser.set(
                "Advanced", "language", data.get("language", "en")
            )  # 🔑 保存语言设置

            if not parser.has_section("Download"):
                parser.add_section("Download")
            parser.set(
                "Download", "concurrent_downloads", str(data["concurrent_downloads"])
            )

            with open(self._config_path, "w", encoding="utf-8") as f:
                parser.write(f)

            gui_logger.info("Configuration saved successfully.")
            return {"success": True}
        except Exception as e:
            gui_logger.error(f"Failed to save config: {e}")
            return {"success": False, "error": str(e)}

    def update_course_config(self, course_id, updates):
        """Update configuration for a specific course"""
        try:
            # 1. Update in-memory list so the UI stays consistent
            course = next((c for c in self.courses if c["id"] == course_id), None)

            # Handle Folder Renaming if alias changed
            if (
                course
                and "alias" in updates
                and updates["alias"] != course.get("alias")
            ):
                try:
                    config = self.load_config()
                    download_dir = Path(config["download_dir"])

                    # Determine old folder name (current alias or original name)
                    old_name = course.get("alias")
                    # If no alias was set, we need to know what the folder name was.
                    # Usually it's the course name if no alias.
                    # But wait, if we are setting an alias for the first time, the folder might be named after the course name.
                    # If we are changing an alias, it's the old alias.

                    # However, 'course' object here is the IN-MEMORY state.
                    # If we just logged in, it has the current state.

                    target_old_name = old_name if old_name else course.get("name")
                    new_name = updates["alias"]

                    if target_old_name and new_name:
                        # Sanitize names just in case (simple check)
                        target_old_name = target_old_name.strip()
                        new_name = new_name.strip()

                        old_path = download_dir / target_old_name
                        new_path = download_dir / new_name

                        if old_path.exists():
                            if not new_path.exists():
                                os.rename(old_path, new_path)
                                gui_logger.info(
                                    f"Renamed folder: '{target_old_name}' -> '{new_name}'"
                                )
                            else:
                                gui_logger.warning(
                                    f"Cannot rename: Target '{new_name}' already exists."
                                )
                except Exception as e:
                    gui_logger.error(f"Folder rename failed: {e}")

            if course:
                course.update(updates)

            # 2. Update persistent storage (courses.json)
            course_config_path = self._config_path.parent / "courses.json"

            # Load existing data
            if course_config_path.exists():
                with open(course_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"courses": {}}

            if "courses" not in data:
                data["courses"] = {}

            # Ensure the entry exists
            if course_id not in data["courses"]:
                data["courses"][course_id] = {}

            entry = data["courses"][course_id]

            # Apply updates
            if "alias" in updates:
                entry["alias"] = updates["alias"]

            if "selected_tabs" in updates:
                entry["selected_tabs"] = updates["selected_tabs"]

            if "sections" in updates:
                # Handle comma-separated string from frontend
                if isinstance(updates["sections"], str):
                    entry["sections"] = [
                        s.strip() for s in updates["sections"].split(",") if s.strip()
                    ]
                else:
                    entry["sections"] = updates["sections"]

            if "skip" in updates:
                entry["skip"] = updates["skip"]

            # Write back to file
            with open(course_config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

            gui_logger.info(f"Updated config for course {course_id}")
            return {"success": True}
        except Exception as e:
            gui_logger.error(f"Failed to update course config: {e}")
            return {"success": False, "error": str(e)}

    def fetch_courses(self):
        """Login and fetch course list (without downloading)"""

        def _run():
            max_retries = 5  # Safari 专用：允许最多重试 2 次
            retry_count = 0

            while retry_count <= max_retries:
                try:
                    # 🔑 使用待保存的配置（如果是新登录），否则使用已保存的配置
                    config = (
                        self._pending_config
                        if self._pending_config
                        else self.load_config()
                    )
                    if not config.get("username") or not config.get("password"):
                        gui_logger.error("Missing credentials.")
                        if self._window:
                            self._window.evaluate_js(
                                "window.syncFailed('Missing credentials')"
                            )
                        self._pending_config = None  # 🔑 清除失败的待保存配置
                        return

                    if retry_count > 0:
                        gui_logger.info(
                            f"Retrying course fetch (attempt {retry_count + 1}/{max_retries + 1})..."
                        )
                    else:
                        gui_logger.info("Fetching course list...")

                    # 1. Login
                    self.driver = get_driver(
                        browser=config["browser"], headless=config["headless"]
                    )
                    auth = PKUAuth(self.driver, webview_window=self._window)
                    self.session, self.courses, error_msg = auth.login(
                        config["username"], config["password"], attempt=retry_count
                    )

                    if not self.session:
                        # 🔑 使用具体的错误消息（如果有的话）
                        error_detail = error_msg if error_msg else "Login failed"
                        raise Exception(error_detail)

                    # 🔑 Close browser immediately after login (session is enough for metadata)
                    if self.driver:
                        gui_logger.info("Login successful, closing browser...")
                        self.driver.quit()
                        self.driver = None

                    # 2. Fetch Metadata (available tabs for each course) - uses session, not browser
                    gui_logger.info("Loading course metadata...")

                    # 🔑 If config hasn't been saved yet (first login), save it now before creating Downloader
                    if self._pending_config and not self._config_path.exists():
                        gui_logger.info(
                            "First login detected, saving config before fetching metadata..."
                        )
                        self.save_config(self._pending_config)

                    cfg = Config(str(self._config_path))
                    downloader = Downloader(self.session, cfg)
                    self.courses = downloader.fetch_metadata(self.courses)

                    # 3. Merge with saved preferences
                    course_config_path = self._config_path.parent / "courses.json"
                    _, prefs = ensure_course_config(course_config_path, self.courses)

                    # 🔑 直接合并配置（ensure_course_config 已经处理了所有默认值）
                    for course in self.courses:
                        p = prefs.get(course["id"], {})
                        course.update(p)

                        # 确保基础字段存在（防御性编程）
                        if "skip" not in course:
                            course["skip"] = False
                        if "selected_tabs" not in course:
                            # 如果 ensure_course_config 没有生成（极端情况），使用空列表
                            course["selected_tabs"] = []

                    # 🔑 4. 持久化完整的课程数据（包括 available_tabs）
                    self._save_all_courses()

                    # 🔑 5. 清除临时配置（已在上面保存过了）
                    if self._pending_config:
                        self._pending_config = None  # 清除临时配置
                        gui_logger.info("First login completed successfully.")

                    # 6. Send to frontend and switch to dashboard
                    if self._window:
                        self._window.evaluate_js(
                            f"window.setCourses({json.dumps(self.courses)})"
                        )
                        self._window.evaluate_js("window.syncComplete()")

                    gui_logger.info(
                        f"  Loaded {len(self.courses)} courses. Configure and click SYNC NOW to download."
                    )
                    return  # 成功，退出重试循环

                except WebDriverException as e:
                    error_msg = str(e).lower()
                    is_session_error = (
                        "invalid session" in error_msg
                        or "session" in error_msg
                        or "connection" in error_msg
                    )
                    is_safari = config.get("browser", "").lower() == "safari"

                    gui_logger.error(f"WebDriver error during fetch: {e}")

                    # Safari 的 session/connection 错误允许重试
                    if is_safari and is_session_error and retry_count < max_retries:
                        gui_logger.warning(
                            f"Safari session/connection error detected, will retry ({retry_count + 1}/{max_retries})..."
                        )
                        retry_count += 1
                        if self.driver:
                            try:
                                self.driver.quit()
                            except:
                                pass
                            self.driver = None
                        time.sleep(2)
                        continue

                    # 其他情况直接报错
                    self._pending_config = None  # 🔑 清除失败的待保存配置
                    if self._window:
                        self._window.evaluate_js(
                            f"window.syncFailed({json.dumps(f'Browser error: {str(e)[:100]}')})"
                        )
                    return

                except Exception as e:
                    gui_logger.error(f"Failed to fetch courses: {e}")

                    # 非 WebDriver 错误，如果是 Safari 且未达重试上限则重试
                    is_safari = config.get("browser", "").lower() == "safari"
                    if is_safari and retry_count < max_retries:
                        gui_logger.warning(
                            f"Safari error, attempting retry ({retry_count + 1}/{max_retries})..."
                        )
                        retry_count += 1
                        if self.driver:
                            try:
                                self.driver.quit()
                            except:
                                pass
                            self.driver = None
                        time.sleep(2)
                        continue

                    self._pending_config = None  # 🔑 清除失败的待保存配置
                    if self._window:
                        self._window.evaluate_js(
                            f"window.syncFailed({json.dumps(str(e))})"
                        )
                    return

                finally:
                    # Ensure browser is closed even on error
                    if self.driver:
                        try:
                            self.driver.quit()
                        except:
                            pass
                        self.driver = None

            # 如果循环结束仍未成功，说明重试全部失败
            self._pending_config = None  # 🔑 清除失败的待保存配置
            gui_logger.error(f"All {max_retries + 1} attempts failed for Safari")
            if self._window:
                self._window.evaluate_js(
                    f"window.syncFailed({json.dumps(f'Failed after {max_retries + 1} attempts. Safari may be unstable.')})"
                )

        threading.Thread(target=_run).start()

    def sync_downloads(self):
        """Execute download for configured courses"""

        def _run():
            max_retries = 2  # Safari 专用：重新登录时允许重试
            retry_count = 0

            while retry_count <= max_retries:
                try:
                    config = self.load_config()

                    # Use existing course list (no need to re-login)
                    if not self.courses:
                        gui_logger.error("No courses loaded. Please login first.")
                        if self._window:
                            self._window.evaluate_js("window.syncFailed('No courses')")
                        return

                    # Re-login if session expired
                    if not self.session:
                        if retry_count > 0:
                            gui_logger.info(
                                f"Retrying re-login (attempt {retry_count + 1}/{max_retries + 1})..."
                            )
                        else:
                            gui_logger.info("Session expired, re-logging in...")

                        self.driver = get_driver(
                            browser=config["browser"], headless=config["headless"]
                        )
                        auth = PKUAuth(self.driver, webview_window=self._window)
                        self.session, _, error_msg = auth.login(
                            config["username"], config["password"], attempt=retry_count
                        )

                        if not self.session:
                            # 🔑 使用具体的错误消息（如果有的话）
                            error_detail = error_msg if error_msg else "Re-login failed"
                            raise Exception(error_detail)

                        # Close browser immediately after login if not headless
                        if self.driver:
                            gui_logger.info("Login successful, closing browser...")
                            self.driver.quit()
                            self.driver = None

                    # Filter active courses (not skipped)
                    active_courses = [
                        c for c in self.courses if not c.get("skip", False)
                    ]

                    if not active_courses:
                        gui_logger.warning("No courses selected for download.")
                        if self._window:
                            self._window.evaluate_js("window.syncComplete()")
                        return

                    gui_logger.info(f"Downloading {len(active_courses)} courses...")

                    # Execute download
                    cfg = Config(str(self._config_path))
                    downloader = Downloader(self.session, cfg)
                    downloader.window = self._window  # Pass window for progress updates
                    downloader.download_courses(active_courses)
                    downloader.print_stats()

                    # Update state
                    self._save_state(
                        {
                            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "last_added": downloader.stats["downloaded"],
                        }
                    )

                    gui_logger.info("  Download completed!")
                    if self._window:
                        self._window.evaluate_js("window.syncComplete()")
                    return  # 成功，退出重试循环

                except WebDriverException as e:
                    error_msg = str(e).lower()
                    is_session_error = (
                        "invalid session" in error_msg
                        or "session" in error_msg
                        or "connection" in error_msg
                    )
                    is_safari = config.get("browser", "").lower() == "safari"

                    gui_logger.error(f"WebDriver error during sync: {e}")

                    # Safari 的 session/connection 错误允许重试
                    if is_safari and is_session_error and retry_count < max_retries:
                        gui_logger.warning(
                            f"Safari session/connection error detected, will retry ({retry_count + 1}/{max_retries})..."
                        )
                        retry_count += 1
                        self.session = None  # 清除失效的 session，下次循环会重新登录
                        if self.driver:
                            try:
                                self.driver.quit()
                            except:
                                pass
                            self.driver = None
                        time.sleep(2)
                        continue

                    # 其他情况直接报错
                    if self._window:
                        self._window.evaluate_js(
                            f"window.syncFailed({json.dumps(f'Browser error: {str(e)[:100]}')})"
                        )
                    return

                except Exception as e:
                    gui_logger.error(f"Download error: {e}")

                    # 非 WebDriver 错误，如果是 Safari 且未达重试上限则重试
                    is_safari = config.get("browser", "").lower() == "safari"
                    if is_safari and retry_count < max_retries and not self.session:
                        # 只在 session 失效时重试（下载逻辑错误不重试）
                        gui_logger.warning(
                            f"Safari error with no session, attempting retry ({retry_count + 1}/{max_retries})..."
                        )
                        retry_count += 1
                        if self.driver:
                            try:
                                self.driver.quit()
                            except:
                                pass
                            self.driver = None
                        time.sleep(2)
                        continue

                    if self._window:
                        self._window.evaluate_js(
                            f"window.syncFailed({json.dumps(str(e))})"
                        )
                    return

                finally:
                    if self.driver:
                        try:
                            self.driver.quit()
                        except:
                            pass
                        self.driver = None

            # 如果循环结束仍未成功，说明重试全部失败
            gui_logger.error(f"All {max_retries + 1} sync attempts failed for Safari")
            if self._window:
                self._window.evaluate_js(
                    f"window.syncFailed({json.dumps(f'Failed after {max_retries + 1} attempts. Safari may be unstable.')})"
                )

        threading.Thread(target=_run).start()

    def login(self, credentials):
        """Initial setup: Save config temporarily and fetch courses. Config is only persisted after successful login."""
        self._pending_config = credentials  # 🔑 暂存配置，等登录成功后再保存
        self.fetch_courses()  # 改为只获取课程列表

    def logout(self):
        """清除所有登录状态和数据，返回登录页"""
        try:
            # 1. 清除内存状态
            self.courses = []
            self.session = None
            self._pending_config = None

            # 2. 删除课程缓存文件
            course_config_path = self._config_path.parent / "courses.json"
            if course_config_path.exists():
                course_config_path.unlink()
                gui_logger.info("Deleted courses.json")

            # 3. 清除配置文件中的凭证（保留其他设置如下载目录、浏览器等）
            config = self.load_config()
            config["username"] = ""
            config["password"] = ""
            self.save_config(config)
            gui_logger.info("Cleared credentials from config")

            # 4. 清除状态文件
            if self._state_path.exists():
                self._state_path.unlink()
                gui_logger.info("Deleted state.json")

            return {"success": True}
        except Exception as e:
            gui_logger.error(f"Logout error: {e}")
            return {"success": False, "error": str(e)}

    def select_folder(self):
        """Open folder selection dialog"""
        if not self._window:
            return None

        import platform

        if platform.system() == "Darwin":  # macOS
            # 🔑 macOS: 使用原生 AppleScript 文件选择器（异步调用）
            def show_native_dialog():
                try:
                    import subprocess

                    # AppleScript 文件选择器
                    script = 'POSIX path of (choose folder with prompt "Select download directory")'
                    result = subprocess.run(
                        ["osascript", "-e", script],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

                    if result.returncode == 0:
                        folder = result.stdout.strip()
                        if folder:
                            # 通过 JS 回调返回结果
                            self._window.evaluate_js(
                                f"window.handleFolderSelected({json.dumps(folder)})"
                            )
                            gui_logger.info(f"Folder selected: {folder}")
                        else:
                            self._window.evaluate_js(
                                "window.handleFolderSelected(null)"
                            )
                    else:
                        # 用户取消或出错
                        gui_logger.info("Folder selection cancelled")
                        self._window.evaluate_js("window.handleFolderSelected(null)")

                except subprocess.TimeoutExpired:
                    gui_logger.error("Folder selection timeout")
                    self._window.evaluate_js("window.handleFolderSelected(null)")
                except Exception as e:
                    gui_logger.error(f"Native dialog error: {e}")
                    self._window.evaluate_js("window.handleFolderSelected(null)")

            # 在新线程中执行（不会阻塞主线程）
            threading.Thread(target=show_native_dialog, daemon=True).start()
            return None
        else:
            # Windows/Linux: 使用 pywebview 的同步调用
            try:
                folder = self._window.create_file_dialog(webview.FOLDER_DIALOG)
                if folder and len(folder) > 0:
                    return folder[0]
            except Exception as e:
                gui_logger.error(f"File dialog error: {e}")
            return None

    def select_folder_direct(self):
        """Direct folder selection (deprecated, kept for compatibility)"""
        # 🔑 macOS 现在使用原生对话框，此方法不再需要
        gui_logger.warning("select_folder_direct called but deprecated on macOS")
        return None

    def get_sync_reports(self, limit=20):
        """Get list of sync reports (newest first)"""
        try:
            reports_dir = self._config_path.parent / "reports"

            if not reports_dir.exists():
                return []

            # Get all JSON files and sort by modification time (newest first)
            report_files = sorted(
                reports_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            # Limit results
            report_files = report_files[:limit]

            reports = []
            for report_file in report_files:
                try:
                    with open(report_file, "r", encoding="utf-8") as f:
                        report = json.load(f)

                    # Extract summary info
                    reports.append(
                        {
                            "sync_id": report["sync_id"],
                            "started_at": report["started_at"],
                            "finished_at": report["finished_at"],
                            "duration_seconds": report.get("duration_seconds", 0),
                            "status": report["status"],
                            "summary": report["summary"],
                        }
                    )
                except Exception as e:
                    gui_logger.error(f"Failed to read report {report_file.name}: {e}")

            return reports

        except Exception as e:
            gui_logger.error(f"Failed to get sync reports: {e}")
            return []

    def get_sync_report(self, sync_id):
        """Get detailed report for a specific sync"""
        try:
            reports_dir = self._config_path.parent / "reports"
            report_file = reports_dir / f"{sync_id}.json"

            if not report_file.exists():
                return {"error": "Report not found"}

            with open(report_file, "r", encoding="utf-8") as f:
                report = json.load(f)

            return report

        except Exception as e:
            gui_logger.error(f"Failed to get sync report {sync_id}: {e}")
            return {"error": str(e)}

    def _load_saved_courses(self):
        """Load course list from courses.json (without re-logging in)"""
        course_config_path = self._config_path.parent / "courses.json"

        if not course_config_path.exists():
            gui_logger.info("No saved courses found.")
            return

        try:
            with open(course_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            courses_data = data.get("courses", {})

            # 🔑 从 JSON 重建课程列表
            self.courses = []
            for course_id, prefs in courses_data.items():
                course = {
                    "id": course_id,
                    "name": prefs.get("name", course_id),
                    "url": prefs.get("url", ""),  # 🔑 添加 url 字段
                    "alias": prefs.get("alias", ""),
                    "skip": prefs.get("skip", False),
                    "selected_tabs": prefs.get("selected_tabs", []),
                    "sections": prefs.get("sections", ["教学内容"]),
                    "available_tabs": prefs.get("available_tabs", []),
                    "flatten": prefs.get("flatten", True),
                }
                self.courses.append(course)

            # 🔑 自动修复历史缓存中 selected_tabs 为空导致全部跳过下载的问题
            if self._ensure_default_selected_tabs_for_courses():
                self._save_all_courses()
                gui_logger.info(
                    "Auto-healed empty selected_tabs to default '教学内容' where applicable."
                )

            gui_logger.info(f"Loaded {len(self.courses)} courses from cache.")
        except Exception as e:
            gui_logger.error(f"Failed to load saved courses: {e}")
            self.courses = []

    def _save_all_courses(self):
        """Save complete course data to courses.json (including available_tabs)"""
        course_config_path = self._config_path.parent / "courses.json"

        try:
            # Load existing data
            if course_config_path.exists():
                with open(course_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {
                    "_note": "Edit per-course preferences. sections accepts a list of course menu names; include '*' to download all sections.",
                    "courses": {},
                }

            # Update all courses
            for course in self.courses:
                course_id = course["id"]

                # Preserve existing config or create new
                if course_id not in data["courses"]:
                    data["courses"][course_id] = {}

                entry = data["courses"][course_id]

                # 🔑 Update all fields (including available_tabs and url)
                entry["name"] = course.get("name", "")
                entry["url"] = course.get("url", "")  # 🔑 保存 URL
                entry["alias"] = course.get("alias", "")
                entry["skip"] = course.get("skip", False)
                entry["selected_tabs"] = course.get("selected_tabs", [])
                entry["sections"] = course.get("sections", ["教学内容"])
                entry["flatten"] = course.get("flatten", True)
                entry["available_tabs"] = course.get(
                    "available_tabs", []
                )  # 🔑 保存标签页列表

            # Write to file
            with open(course_config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

            gui_logger.info("Saved course data to JSON.")
        except Exception as e:
            gui_logger.error(f"Failed to save courses: {e}")

    def open_file(self, file_path):
        """Open file with system default application."""
        import subprocess
        import platform

        try:
            # Convert to Path object for validation
            file_path_obj = Path(file_path).resolve()
            config = self.load_config()
            download_dir = Path(config["download_dir"]).resolve()

            # Security check: ensure file is within download directory
            if not str(file_path_obj).startswith(str(download_dir)):
                gui_logger.error(
                    f"Security: Attempted to open file outside download directory: {file_path}"
                )
                return {"success": False, "error": "File path not allowed"}

            # Check if file exists
            if not file_path_obj.exists():
                gui_logger.warning(f"File not found: {file_path}")
                return {"success": False, "error": "File not found or has been moved"}

            # Open file with platform-specific command
            system = platform.system()
            if system == "Darwin":  # macOS
                subprocess.run(["open", str(file_path_obj)], check=True)
            elif system == "Windows":
                os.startfile(str(file_path_obj))
            else:  # Linux and others
                subprocess.run(["xdg-open", str(file_path_obj)], check=True)

            gui_logger.info(f"Opened file: {file_path_obj.name}")
            return {"success": True}

        except subprocess.CalledProcessError as e:
            gui_logger.error(f"Failed to open file: {e}")
            return {
                "success": False,
                "error": "Failed to open file with default application",
            }
        except Exception as e:
            gui_logger.error(f"Error opening file: {e}")
            return {"success": False, "error": str(e)}

    def open_folder(self, course_name):
        """Open course folder in file manager."""
        import subprocess
        import platform

        try:
            config = self.load_config()
            download_dir = Path(config["download_dir"]).resolve()
            folder_path = (download_dir / course_name).resolve()

            # Security check: ensure folder is within download directory
            if not str(folder_path).startswith(str(download_dir)):
                gui_logger.error(
                    f"Security: Attempted to open folder outside download directory: {folder_path}"
                )
                return {"success": False, "error": "Folder path not allowed"}

            # Create folder if it doesn't exist
            if not folder_path.exists():
                gui_logger.info(f"Creating folder: {folder_path}")
                folder_path.mkdir(parents=True, exist_ok=True)

            # Open folder with platform-specific command
            system = platform.system()
            if system == "Darwin":  # macOS
                subprocess.run(["open", str(folder_path)], check=True)
            elif system == "Windows":
                os.startfile(str(folder_path))
            else:  # Linux and others
                subprocess.run(["xdg-open", str(folder_path)], check=True)

            gui_logger.info(f"Opened folder: {course_name}")
            return {"success": True}

        except subprocess.CalledProcessError as e:
            gui_logger.error(f"Failed to open folder: {e}")
            return {"success": False, "error": "Failed to open folder in file manager"}
        except Exception as e:
            gui_logger.error(f"Error opening folder: {e}")
            return {"success": False, "error": str(e)}

    def refresh_stats(self):
        """Refresh local file statistics"""
        try:
            config = self.load_config()
            local_stats = self._scan_local_files(config["download_dir"])
            gui_logger.info("Local statistics refreshed")
            return {"success": True, "local_stats": local_stats}
        except Exception as e:
            gui_logger.error(f"Failed to refresh stats: {e}")
            return {"success": False, "error": str(e)}


def main():
    if sys.version_info >= (3, 14):
        print(
            "Error: PKU-Get GUI currently does not support Python 3.14+ on Windows because pythonnet/pywebview WinForms ABI is not yet available."
        )
        print(
            "Please use Python 3.13 (recommended) or 3.12, then recreate the virtual environment."
        )
        return

    api = Api()

    # Check for dev server or built files
    dev_url = "http://localhost:5173"
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("localhost", 5173))
    sock.close()

    if result == 0:
        url = dev_url
        print(f"Loading from Dev Server: {url}")
    else:
        # Fallback to built files
        dist_path = os.path.join(os.path.dirname(__file__), "gui", "dist", "index.html")
        if not os.path.exists(dist_path):
            print("Error: GUI not built.")
            print("Please run 'cd gui && npm run build' to generate the interface.")
            return
        else:
            try:
                with open(dist_path, "r", encoding="utf-8") as f:
                    html = f.read()

                script_paths = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
                style_paths = re.findall(r'<link[^>]+href=["\']([^"\']+)["\']', html)
                referenced_assets = [
                    p
                    for p in (script_paths + style_paths)
                    if p and not p.startswith(("http://", "https://", "data:"))
                ]

                missing_assets = []
                dist_dir = os.path.dirname(dist_path)
                for rel_path in referenced_assets:
                    cleaned = rel_path.lstrip("./\\").replace("/", os.sep)
                    asset_abs = os.path.join(dist_dir, cleaned)
                    if not os.path.exists(asset_abs):
                        missing_assets.append(rel_path)

                if missing_assets:
                    print("Error: GUI build assets are incomplete or outdated.")
                    print("Missing files referenced by dist/index.html:")
                    for item in missing_assets:
                        print(f"  - {item}")
                    print("Please run 'cd gui && npm run build' and restart.")
                    return
            except Exception as e:
                print(f"Warning: Failed to validate GUI assets: {e}")

            url = f"file://{os.path.abspath(dist_path)}"
            print(f"Loading from File: {url}")

    window = webview.create_window(
        "PKU-Get | 未名拾课",
        url,
        width=1100,
        height=800,
        resizable=True,
        js_api=api,
        background_color="#0f172a",
    )

    # Set window AFTER creation, but handler is already safe
    api.set_window(window)

    # Ensure pywebview is ready before frontend tries to access API
    def on_loaded():
        # 🔑 给 JS 桥接更多时间完全初始化
        time.sleep(0.2)  # 增加到 200ms
        try:
            # 触发自定义事件通知前端
            window.evaluate_js("window.dispatchEvent(new Event('pywebviewready'))")
            gui_logger.info("pywebview API ready signal sent")
        except Exception as e:
            gui_logger.error(f"Failed to send ready signal: {e}")

    window.events.loaded += on_loaded

    webview.start(debug=False)


if __name__ == "__main__":
    main()
