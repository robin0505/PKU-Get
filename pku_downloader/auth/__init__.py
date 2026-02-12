"""
Authentication module - Login to PKU's terrible website.
This code exists because PKU can't implement proper API authentication.
"""
import time
import sys
import requests
import re
from typing import Tuple, List, Dict, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, WebDriverException
from urllib.parse import urljoin

from ..logger import get_logger

logger = get_logger('auth')


class LoginError(Exception):
    """自定义登录错误异常，用于区分密码错误等具体登录失败原因"""
    pass


class PKUAuth:
    """Handle PKU's overcomplicated login system."""
    
    LOGIN_URL = 'https://course.pku.edu.cn/'
    IAAA_DOMAIN = 'iaaa.pku.edu.cn'
    HOME_URL_MARKER = 'portal/execute/tabs/tabAction'
    
    def __init__(self, driver, webview_window=None):
        self.driver = driver
        self.webview_window = webview_window
        self.session = None
        self.courses = []
    
    def login(self, username: str, password: str, attempt: int = 0) -> Tuple[Optional[requests.Session], List[Dict], Optional[str]]:
        """
        Login and get session with courses.
        Returns (session, courses, error_message).
        - 成功: (session, courses, None)
        - 失败: (None, [], error_message)

        Args:
            username: Student ID
            password: Password
            attempt: Current attempt number (0 for first try, 1+ for retries)
        """
        try:
            self._navigate_to_login(attempt=attempt)
            self._perform_login(username, password)
            self._wait_for_home()  # 内部会检查错误并恢复窗口
            self.courses = self._extract_courses()
            self.session = self._create_session()
            return self.session, self.courses, None

        except LoginError as e:
            # 密码错误等登录失败（明确的错误消息）
            error_msg = str(e)
            logger.error(f"Login failed with error: {error_msg}")
            return None, [], error_msg

        except TimeoutException as e:
            logger.error(f"Login timeout: {e}")
            return None, [], "登录超时，请检查网络连接"

        except WebDriverException as e:
            logger.error(f"Browser error during login: {e}")
            return None, [], f"浏览器错误: {str(e)[:100]}"

        except Exception as e:
            logger.error(f"Login failed with unexpected error: {e}")
            return None, [], f"未知错误: {str(e)[:100]}"

        finally:
            # 🔑 确保窗口始终恢复显示（无论成功还是失败）
            if self.webview_window:
                try:
                    logger.info("[AUTH] Finally block: ensuring pywebview window is visible...")
                    self.webview_window.show()
                except Exception as e:
                    logger.warning(f"[AUTH] Failed to show pywebview window in finally: {e}")
    
    def _navigate_to_login(self, attempt: int = 0):
        """Go to login page and click the campus card link.
        
        Args:
            attempt: Current attempt number (0 for first try, 1+ for retries)
        """
        # Hide pywebview window before opening Safari to avoid blocking
        if self.webview_window:
            try:
                logger.info("[AUTH] Hiding pywebview window to avoid blocking Safari...")
                self.webview_window.hide()
            except Exception as e:
                logger.warning(f"[AUTH] Failed to hide pywebview window: {e}")
        
        logger.info("[AUTH] Opening course portal login page...")
        logger.debug(f"[AUTH] Current URL before get: {getattr(self.driver, 'current_url', 'N/A')}")

        self.driver.get(self.LOGIN_URL)

        logger.info("[AUTH] Navigating to login page...")

        # Wait for page to fully load (especially important for Safari)
        body = WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        logger.debug(f"[AUTH] Login page body loaded, URL={self.driver.current_url}")
        logger.debug(f"[AUTH] Body text (first 200 chars)={body.text[:200]!r}")
        time.sleep(1)  # Extra buffer for Safari's slower rendering
        
        # 判定是否为 Safari：优先使用 driver 上的标记，避免再执行 JS 拿 UA
        is_safari = bool(getattr(self.driver, "is_safari", False))
        logger.debug(f"[AUTH] is_safari flag from driver={is_safari}")

        try:
            elems = self.driver.find_elements(By.XPATH, "//*[contains(text(), '校园卡用户')]")
            logger.debug(f"[AUTH] Found {len(elems)} elements containing '校园卡用户'")
            for i, el in enumerate(elems):
                try:
                    logger.debug(
                        f"[AUTH] elem[{i}]: tag={el.tag_name}, "
                        f"displayed={el.is_displayed()}, "
                        f"enabled={el.is_enabled()}, "
                        f"text={el.text!r}"
                    )
                except Exception as e:
                    logger.debug(f"[AUTH] elem[{i}] inspect failed: {e}")
        except Exception as e:
            logger.debug(f"[AUTH] Failed to scan elems for '校园卡用户': {e}")

        # Click "校园卡用户" - why not just redirect automatically? Because PKU.
        logger.info("[AUTH] Waiting for '校园卡用户' link to become clickable...")
        campus_link = WebDriverWait(self.driver, 20).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "校园卡用户"))
        )
        logger.debug("[AUTH] Found campus card link element")

        # Scroll into view
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", campus_link)
            logger.debug("[AUTH] Scrolled campus link into view")
        except Exception as e:
            logger.warning(f"[AUTH] scrollIntoView failed: {e}")
        time.sleep(0.8)

        # ------- 统一使用原生 click，避免 JS 跳转触发验证码 -------
        
        click_error = None
        try:
            logger.info("[AUTH] Trying normal click on campus link...")
            campus_link.click()
            logger.debug("[AUTH] Normal click on campus link succeeded")
        except Exception as e:
            click_error = e
            logger.warning(f"[AUTH] Normal click failed: {e}, using JavaScript click fallback")
            try:
                self.driver.execute_script("arguments[0].click();", campus_link)
                logger.debug("[AUTH] JavaScript click on campus link succeeded")
            except Exception as js_e:
                logger.error(f"[AUTH] JavaScript click on campus link also failed: {js_e}")
                raise

        logger.debug(f"[AUTH] After click, current URL={self.driver.current_url}")

        # For Safari & others: 记录窗口句柄
        try:
            handles = self.driver.window_handles
            logger.debug(f"[AUTH] Window handles after click/navigation: {handles}")
        except Exception as e:
            logger.debug(f"[AUTH] Failed to get window_handles: {e}")

        # 等待跳转到 IAAA（通用逻辑，所有浏览器共用）
        # 第一次尝试使用较短超时（5秒），因为通常会失败；后续重试使用15秒
        timeout = 5 if attempt == 0 else 15
        logger.info(f"[AUTH] Waiting for redirect to IAAA page (timeout={timeout}s, attempt={attempt})...")

        start = time.time()
        last_log = start
        while True:
            current = time.time()
            if current - start > timeout:
                logger.error(f"[AUTH] Timeout waiting for IAAA. last_url={self.driver.current_url}")
                try:
                    logger.error(f"[AUTH] Final window handles before timeout: {self.driver.window_handles}")
                except Exception as e:
                    logger.error(f"[AUTH] Failed to get window_handles on timeout: {e}")
                raise TimeoutException("Timeout waiting for redirect to IAAA")

            try:
                if self.IAAA_DOMAIN in getattr(self.driver, 'current_url', ''):
                    logger.info(f"[AUTH] Redirected to IAAA: {self.driver.current_url}")
                    break
            except Exception as e:
                logger.debug(f"[AUTH] Error reading current_url while waiting for IAAA: {e}")

            if current - last_log > 3:
                last_log = current
                try:
                    logger.info(f"[AUTH] Still waiting for IAAA, current_url={self.driver.current_url}")
                except Exception:
                    logger.info("[AUTH] Still waiting for IAAA, current_url=<unavailable>")
            time.sleep(0.5)
            
    def _perform_login(self, username: str, password: str):
        """Fill in credentials and submit."""
        logger.info("Waiting for login form...")
        time.sleep(1.5)

        # Find form elements with longer timeout for Safari
        user_field = WebDriverWait(self.driver, 20).until(
            EC.visibility_of_element_located((By.ID, "user_name"))
        )
        pass_field = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.ID, "password"))
        )
        login_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "logon_button"))
        )

        logger.debug("Login form loaded, filling credentials...")

        # Fill username with slight pacing
        user_field.clear()
        for ch in username:
            user_field.send_keys(ch)
            time.sleep(0.03)  # small per-char delay to mimic human typing

        # 等一等再输密码，避免输得太快触发反爬
        time.sleep(1.5)

        # Fill password with slower per-char pacing to reduce bot detection
        pass_field.clear()
        for ch in password:
            pass_field.send_keys(ch)
            time.sleep(0.08)  # slower per-char delay for password

        time.sleep(0.5)  # PKU's server needs a moment to think

        # Try clicking, if blocked use JavaScript
        try:
            login_btn.click()
            logger.debug("Login button clicked")
        except ElementClickInterceptedException:
            logger.debug("Click intercepted, using JavaScript fallback")
            self.driver.execute_script("arguments[0].click();", login_btn)
        except Exception as e:
            logger.warning(f"Failed to click login button: {e}, trying JavaScript")
            self.driver.execute_script("arguments[0].click();", login_btn)

    def _check_login_error(self):
        """
        检查登录页面是否显示错误消息。
        如果发现错误，抛出 LoginError 异常。

        北大登录系统的错误消息显示在 <span id="msg"> 元素中，格式为：
        $("#msg").html("<i class=\"fa fa-minus-circle\"></i> 错误消息文本")

        可能的错误消息包括：
        - "用户名或密码错误"
        - "账号不能为空"
        - "密码不能为空"
        - "验证码错误"
        - "短信验证码错误或已过期"
        - "手机令牌错误或已过期"
        - "账号未激活"
        - "系统服务异常"
        - "密码强度不足"

        注意：登录过程中会显示"正在登录..."，这不是错误，应该忽略。
        """
        try:
            # 等待几秒让AJAX请求完成并显示错误消息
            time.sleep(2.5)

            # 尝试查找错误消息元素
            msg_elem = self.driver.find_element(By.ID, "msg")

            if msg_elem and msg_elem.is_displayed():
                # 获取错误消息文本
                error_html = msg_elem.get_attribute('innerHTML') or ''
                error_text = msg_elem.text.strip()

                logger.debug(f"Found msg element: innerHTML={error_html!r}, text={error_text!r}")

                # 使用正则表达式清理HTML标签，提取纯文本
                # 例如：'<i class="fa fa-minus-circle"></i> 用户名或密码错误' -> '用户名或密码错误'
                clean_text = re.sub(r'<[^>]+>', '', error_html).strip()

                # 忽略"正在登录..."状态消息（这是进行中状态，不是错误）
                if clean_text and "正在登录" not in clean_text and "Logging In" not in clean_text and clean_text != "":
                    # 发现实际的错误消息
                    logger.error(f"Login error detected: {clean_text}")
                    raise LoginError(clean_text)
                else:
                    logger.debug(f"msg element contains non-error text: {clean_text!r}")
            else:
                logger.debug("msg element not found or not displayed")

        except NoSuchElementException:
            # 没有错误元素，说明没有错误
            logger.debug("No error message element found (normal case)")
            pass
        except LoginError:
            # 重新抛出LoginError
            raise
        except Exception as e:
            # 其他异常记录但不影响流程
            logger.debug(f"Error while checking for login error: {e}")

    def _wait_for_home(self):
        """
        等待登录完成：成功跳转到主页 OR 显示错误消息。
        使用轮询方式同时检查两个条件，避免长时间等待超时。
        """
        logger.info("Waiting for login result (success redirect or error message)...")

        max_wait = 40  # 最大等待40秒
        check_interval = 0.5  # 每0.5秒检查一次
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                # 条件1：检查是否成功跳转到主页
                current_url = self.driver.current_url
                if self.HOME_URL_MARKER in current_url:
                    logger.info(f"Successfully redirected to home: {current_url}")

                    # 成功登录，恢复pywebview窗口
                    if self.webview_window:
                        try:
                            logger.info("[AUTH] Restoring pywebview window after successful login...")
                            self.webview_window.show()
                        except Exception as e:
                            logger.warning(f"[AUTH] Failed to restore pywebview window: {e}")

                    return  # 成功，退出

                # 条件2：检查是否显示错误消息（直接在这里检查，不调用_check_login_error）
                try:
                    msg_elem = self.driver.find_element(By.ID, "msg")
                    if msg_elem and msg_elem.is_displayed():
                        error_html = msg_elem.get_attribute('innerHTML') or ''
                        clean_text = re.sub(r'<[^>]+>', '', error_html).strip()

                        # 如果有非"正在登录"的消息，说明是错误
                        if clean_text and "正在登录" not in clean_text and "Logging In" not in clean_text and clean_text != "":
                            logger.error(f"Login error detected in wait loop: {clean_text}")
                            # 直接抛出，不再调用 _check_login_error
                            raise LoginError(clean_text)
                except NoSuchElementException:
                    pass  # 没有消息元素，继续等待
                except LoginError:
                    # 立即重新抛出，跳出while循环
                    raise

            except LoginError:
                # 🔑 LoginError 必须立即抛出，不能被下面的 Exception 捕获
                raise
            except Exception as e:
                # 其他异常只记录日志，继续循环
                logger.debug(f"Non-critical error during wait check: {e}")

            # 等待一小段时间再检查
            time.sleep(check_interval)

        # 超时仍未成功跳转也未出现错误消息
        logger.error(f"Timeout waiting for login result. Final URL: {self.driver.current_url}")

        # 超时前最后检查一次是否有错误消息
        try:
            msg_elem = self.driver.find_element(By.ID, "msg")
            if msg_elem and msg_elem.is_displayed():
                error_html = msg_elem.get_attribute('innerHTML') or ''
                clean_text = re.sub(r'<[^>]+>', '', error_html).strip()
                if clean_text and "正在登录" not in clean_text and "Logging In" not in clean_text:
                    raise LoginError(clean_text)
        except NoSuchElementException:
            pass

        # 没有错误消息但超时了，抛出TimeoutException
        raise TimeoutException("Timeout waiting for redirect to home page")
    
    def _extract_courses(self) -> List[Dict]:
        """Extract course list from the page."""
        courses = []
        
        try:
            # Wait a bit for dynamic content
            time.sleep(2)
            
            # 1. 首先提取学生课程（当前学期的课程）
            try:
                course_list = WebDriverWait(self.driver, 25).until(
                    EC.visibility_of_element_located((
                        By.CSS_SELECTOR, 
                        "#module\\:_141_1 ul.portletList-img.courseListing"
                    ))
                )
                student_courses = self._extract_courses_from_list(course_list)
                courses.extend(student_courses)
                logger.info(f"Found {len(student_courses)} student courses")
            except Exception as e:
                logger.warning(f"Failed to extract student courses: {e}")
            
            # 2. 然后提取助教课程
            try:
                # 查找助教课程区域
                ta_sections = self.driver.find_elements(By.XPATH, "//h3[contains(text(), '在以下课程中，您是助教')]/following-sibling::ul[contains(@class, 'courseListing')]")
                for ta_section in ta_sections:
                    ta_courses = self._extract_courses_from_list(ta_section)
                    # 为助教课程添加标记
                    for course in ta_courses:
                        course['is_ta'] = True
                        course['name'] = f"[助教] {course['name']}"
                    courses.extend(ta_courses)
                    logger.info(f"Found {len(ta_courses)} TA courses")
            except Exception as e:
                logger.warning(f"Failed to extract TA courses: {e}")
            
            # 3. 查找所有其他可能的课程列表（作为备选）
            try:
                # 查找 module:_141_1 中的所有课程列表（不只是第一个）
                all_course_lists = self.driver.find_elements(By.CSS_SELECTOR, "#module\\:_141_1 ul.portletList-img.courseListing")
                for i, course_list in enumerate(all_course_lists):
                    if i == 0:  # 跳过第一个，已经处理过了
                        continue
                    additional_courses = self._extract_courses_from_list(course_list)
                    # 检查是否已经在列表中，避免重复
                    for course in additional_courses:
                        if not any(c['id'] == course['id'] for c in courses):
                            courses.append(course)
                logger.info(f"Total courses found: {len(courses)}")
            except Exception as e:
                logger.warning(f"Failed to extract additional courses: {e}")
                
        except Exception as e:
            logger.error(f"Error extracting courses: {e}")
        
        return courses
    
    def _extract_courses_from_list(self, course_list_element) -> List[Dict]:
        """从课程列表元素中提取课程信息"""
        courses = []
        
        try:
            # Get all course links
            links = course_list_element.find_elements(By.CSS_SELECTOR, 'li a')
            
            for link in links:
                raw = link.text.strip()
                # 支持英文冒号和中文冒号，取最后一个冒号之后到第一个左括号之前的内容
                colon_pos = max(raw.rfind(':'), raw.rfind('：'))
                start = colon_pos + 1 if colon_pos != -1 else 0
                paren_pos = raw.find('(', start)
                end = paren_pos if paren_pos != -1 else len(raw)
                name = raw[start:end].strip()
                
                url = link.get_attribute('href')
                # Extract course ID from URL
                course_id = None
                if url and 'id=PkId{key=' in url:
                    try:
                        start = url.find('id=PkId{key=') + len('id=PkId{key=')
                        end = url.find(',', start)
                        if end != -1:
                            course_id = url[start:end]
                    except Exception as e:
                        logger.debug(f"Failed to parse course ID from URL: {e}")
                        pass
                
                if name and course_id and url:
                    courses.append({
                        'name': name,
                        'id': course_id,
                        'url': urljoin(self.driver.current_url, url)
                    })
        except Exception as e:
            logger.error(f"Error extracting courses from list: {e}")
        
        return courses
    
    def _create_session(self) -> requests.Session:
        """Create requests session with browser cookies."""
        session = requests.Session()
        
        # Copy user agent
        user_agent = self.driver.execute_script("return navigator.userAgent;")
        session.headers.update({'User-Agent': user_agent})
        
        # Copy cookies
        for cookie in self.driver.get_cookies():
            if 'name' in cookie and 'value' in cookie:
                session.cookies.set(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie.get('domain'),
                    path=cookie.get('path', '/'),
                    secure=cookie.get('secure', False),
                    expires=cookie.get('expiry')
                )
        
        return session