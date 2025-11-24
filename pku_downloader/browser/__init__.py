"""
Browser driver management.
Supports Chrome, Firefox, Edge, and Safari.
"""
import platform
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from selenium.common.exceptions import WebDriverException, SessionNotCreatedException
from selenium.webdriver.safari.service import Service as SafariService
from .edge_utils import install_edge_driver_silently
from ..logger import get_logger

logger = get_logger('browser')

def get_driver(browser: str = 'edge', headless: bool = True):
    """
    获取浏览器驱动。
    默认逻辑：优先使用 Edge，并在失败时自动修补驱动。
    """
    # 简单归一化
    b = browser.lower()

    # Safari on macOS - doesn't support headless mode
    if platform.system() == 'Darwin' and (b == 'safari' or b not in ['chrome', 'firefox', 'edge']):
        if headless:
            logger.warning("Safari does not support headless mode, running in normal mode")
        return _get_safari()

    # 只要不是 Mac Safari，默认都走 Edge 逻辑
    if b == 'firefox':
        return _get_firefox(headless)
    elif b == 'chrome':
        return _get_chrome(headless)

    return _get_edge(headless)

def _get_base_path():
    """获取软件运行根目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.getcwd()

def _get_driver_dir():
    """
    获取驱动存储目录 (driver/)
    如果不存在会自动创建。
    """
    base_path = _get_base_path()
    driver_dir = os.path.join(base_path, 'driver')
    
    # 确保文件夹存在
    if not os.path.exists(driver_dir):
        try:
            os.makedirs(driver_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"无法创建 driver 目录: {e}，将回退到根目录")
            return base_path
            
    return driver_dir

def _get_edge(headless: bool = True):
    options = webdriver.EdgeOptions()
    if headless:
        options.add_argument('--headless')
    
    # 常用防报错参数
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1280,800')
    options.add_argument('--log-level=3')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    # 移除自动化特征
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    # 1. 确定路径：driver/msedgedriver.exe
    driver_dir = _get_driver_dir()
    driver_name = "msedgedriver.exe"
    driver_path = os.path.join(driver_dir, driver_name)

    # 2. 预检查：如果本地没驱动，先下载到 driver 目录
    if not os.path.exists(driver_path):
        logger.info(f"本地未发现驱动，正在初始化下载到: {driver_dir} ...")
        install_edge_driver_silently(driver_dir)

    # 3. 尝试启动
    service = EdgeService(executable_path=driver_path) if os.path.exists(driver_path) else None
    
    try:
        driver = webdriver.Edge(service=service, options=options)
        return driver
        
    except (SessionNotCreatedException, WebDriverException) as e:
        logger.warning(f"Edge 启动失败 (可能是版本不匹配)，尝试自动修复... 错误: {str(e)[:50]}")
        
        # 4. 自动修复：强制重新下载覆盖
        success = install_edge_driver_silently(driver_dir)
        
        if success:
            try:
                # 修复后重试
                service = EdgeService(executable_path=driver_path)
                driver = webdriver.Edge(service=service, options=options)
                logger.info("自动修复完成，浏览器成功启动！")
                return driver
            except Exception as retry_e:
                logger.error(f"重试依然失败: {retry_e}")
        
        # 5. 彻底失败
        raise Exception("Edge 驱动自动适配失败，请检查网络是否能访问 npmmirror.com")


def _get_chrome(headless: bool = True):
    """Initialize Chrome WebDriver."""
    options = webdriver.ChromeOptions()
    if headless: options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1280,800')
    options.add_argument('--log-level=3')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(5)
    return driver

def _get_firefox(headless: bool = True):
    """Initialize Firefox WebDriver."""
    options = webdriver.FirefoxOptions()
    if headless: options.add_argument('--headless')
    options.add_argument('--width=1280')
    options.add_argument('--height=800')

    service = FirefoxService(GeckoDriverManager().install())
    driver = webdriver.Firefox(service=service, options=options)
    driver.implicitly_wait(5)
    return driver

def _get_safari():
    if platform.system() != 'Darwin':
        raise Exception("Safari is only available on macOS.")

    logger.info("Initializing Safari driver...")

    # Safari requires "Allow Remote Automation" to be enabled in Develop menu
    try:
        # --- 修改开始 ---
        # 显式指定 macOS 系统自带的 safaridriver 路径
        # 这样可以绕过 Selenium Manager 的自动查找，避免 PyInstaller 打包后的路径错误
        service = SafariService(executable_path='/usr/bin/safaridriver')
        
        driver = webdriver.Safari(service=service)
        # --- 修改结束 ---

        driver.set_window_size(1280, 800)
        driver.implicitly_wait(10)  # Increased for Safari's slower performance
        
        # 标记这是 Safari，方便其他模块无需再执行 JS 检测 UA
        try:
            setattr(driver, "is_safari", True)
        except Exception:
            pass
        logger.info("Safari driver initialized successfully")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize Safari: {e}")
        logger.error("Make sure 'Allow Remote Automation' is enabled in Safari > Develop menu")
        raise