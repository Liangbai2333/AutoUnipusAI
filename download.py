import requests
from tqdm import tqdm
import os
import atexit
import uuid

from log import logger

url_to_file_cache = {}

def cleanup_downloaded_file(file_path):
    """
    清理已下载的文件

    :param file_path: 文件路径
    """
    if os.path.exists(file_path):
        os.remove(file_path)

def using_cached_file(suffix, save_dir=".cache") -> str:
    # 注册清理函数
    file_name = str(uuid.uuid4()) + "." + suffix  # 例如：f47ac10b-58cc-4372-a567-0e02b2c3d479.tmp
    save_path = os.path.join(save_dir, file_name)
    atexit.register(cleanup_downloaded_file, save_path)
    return save_path

def download_cache_file(url, suffix, save_dir=".cache") -> str:
    """
    下载文件并显示进度条，使用随机文件名

    :param suffix: 文件后缀
    :param url: 文件的下载链接
    :param save_dir: 文件保存目录
    :return 文件地址
    """
    # 如果 URL 已缓存，直接返回缓存的文件路径
    if url in url_to_file_cache:
        logger.info(f"URL 已缓存，直接返回文件: {url_to_file_cache[url]}")
        return url_to_file_cache[url]

    # 生成随机文件名（使用 UUID）
    file_name = str(uuid.uuid4()) + "." + suffix  # 例如：f47ac10b-58cc-4372-a567-0e02b2c3d479.tmp
    # 下载文件
    save_path = download_file(url, save_dir, file_name)
    # 注册清理函数
    atexit.register(cleanup_downloaded_file, save_path)
    url_to_file_cache[url] = save_path
    return save_path

def download_file(url, save_dir, file_name) -> str:
    # 创建保存目录
    os.makedirs(save_dir, exist_ok=True)
    # 发起请求，获取文件信息
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get("content-length", 0))  # 获取文件总大小
    save_path = os.path.join(save_dir, file_name)

    # 使用 tqdm 显示进度条
    with open(save_path, "wb") as file, tqdm(
            desc=file_name,  # 进度条描述（文件名）
            total=total_size,  # 总大小
            unit="B",  # 单位
            unit_scale=True,  # 自动缩放单位（如 KB、MB）
            unit_divisor=1024,  # 单位除数
    ) as pbar:
        for chunk in response.iter_content(chunk_size=1024):  # 分块下载
            if chunk:
                file.write(chunk)  # 写入文件
                pbar.update(len(chunk))  # 更新进度条

    logger.info(f"文件已下载到: {save_path}")
    return save_path