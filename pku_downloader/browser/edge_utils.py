import os
import sys
import logging
import zipfile
import io
import platform
import requests
import urllib3

# 禁用 SSL 警告 (因为我们会用 verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger('edge_utils')

def get_edge_version():
    """从注册表读取 Windows Edge 精确版本"""
    if platform.system() != 'Windows':
        return None
    
    import winreg
    try:
        # 路径1：当前用户安装
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Edge\BLBeacon")
        version, _ = winreg.QueryValueEx(key, "version")
        return version
    except:
        pass
    try:
        # 路径2：系统级安装
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}")
        version, _ = winreg.QueryValueEx(key, "pv")
        return version
    except:
        return None

def install_edge_driver_silently(target_dir):
    """
    自动下载 Edge 驱动。
    策略：优先微软官方 -> 失败则走阿里云镜像 (npmmirror)。
    """
    version = get_edge_version()
    if not version:
        logger.error("无法检测到 Edge 版本，无法自动下载。")
        return False

    # 定义下载源列表
    urls = [
        {
            "name": "Microsoft Azure",
            "url": f"https://msedgedriver.azureedge.net/{version}/edgedriver_win64.zip"
        },
        {
            "name": "Aliyun Mirror", # 国内用户的救星
            "url": f"https://npmmirror.com/mirrors/edgedriver/{version}/edgedriver_win64.zip"
        }
    ]

    for source in urls:
        name = source["name"]
        url = source["url"]
        
        logger.info(f"正在尝试从 [{name}] 更新驱动 (v{version})...")
        try:
            # verify=False 是关键，防止校内网 SSL 拦截报错
            resp = requests.get(url, stream=True, timeout=20, verify=False)
            resp.raise_for_status()
            
            # 解压逻辑
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                found = False
                for filename in z.namelist():
                    if "msedgedriver.exe" in filename:
                        # 直接解压到 target_dir
                        target_path = os.path.join(target_dir, "msedgedriver.exe")
                        with open(target_path, 'wb') as f:
                            f.write(z.read(filename))
                        found = True
                        break
                
                if found:
                    logger.info(f"驱动更新成功！来源: {name}")
                    return True
                else:
                    logger.warning(f"下载的 Zip 包中未找到 msedgedriver.exe")

        except Exception as e:
            logger.warning(f"[{name}] 下载失败: {e}")
            continue # 试下一个源

    logger.error("所有镜像源均无法下载驱动，请检查网络。")
    return False