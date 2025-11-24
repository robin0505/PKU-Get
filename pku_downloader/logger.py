"""
Logging configuration for PKU Downloader.
Unified logging management.
"""
import logging
import sys
from pathlib import Path

def setup_logger(log_file: str = None, level: int = logging.INFO):
    """
    全局日志初始化。
    配置 Root Logger，确保所有模块的日志都能被捕获到控制台和文件。
    """
    # 1. 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 防止重复添加 Handler (例如 GUI 重启时)
    if root_logger.handlers:
        # 如果已经配置过，只更新 level，不重复添加 Handler
        root_logger.setLevel(level)
        return root_logger

    # 2. 定义通用格式
    # 控制台用简洁格式，文件用详细格式
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 3. 配置控制台输出 (Stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 4. 配置文件输出
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            # 文件通常记录更详细的日志，可以设为 DEBUG 或跟随全局 level
            file_handler.setLevel(logging.DEBUG) 
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to setup file logging: {e}")

    # 5. 屏蔽第三方库的噪音 (可选)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("pywebview").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str = None):
    """
    获取子模块的 Logger。
    例如 get_logger('browser') -> 'pku_downloader.browser'
    """
    # 统一前缀，方便管理
    prefix = 'pku_downloader'
    if name:
        return logging.getLogger(f'{prefix}.{name}')
    return logging.getLogger(prefix)