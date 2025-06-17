import requests
from tqdm import tqdm
import os
import hashlib
from urllib.parse import urlparse

from util.log import logger


def get_url_hash(url: str) -> str:
    """
    根据URL生成哈希值作为文件名

    Args:
        url: 下载链接

    Returns:
        str: URL的MD5哈希值
    """
    return hashlib.md5(url.encode('utf-8')).hexdigest()


def get_file_extension_from_url(url: str) -> str:
    """
    从URL中提取文件扩展名

    Args:
        url: 下载链接

    Returns:
        str: 文件扩展名（不含点号），如果无法确定则返回空字符串
    """
    parsed_url = urlparse(url)
    path = parsed_url.path
    if '.' in path:
        return path.split('.')[-1].lower()
    return ""


def download_file(url: str, save_dir: str = ".cache", custom_filename: str = None,
                  force_extension: str = None) -> str:
    """
    下载文件并永久缓存，使用URL哈希值作为文件名

    Args:
        url: 文件的下载链接
        save_dir: 文件保存目录，默认为 .cache
        custom_filename: 自定义文件名（可选），如果提供则不使用哈希值
        force_extension: 强制指定文件扩展名（可选）

    Returns:
        str: 下载文件的本地路径
    """
    # 创建保存目录
    os.makedirs(save_dir, exist_ok=True)

    # 确定文件名
    if custom_filename:
        file_name = custom_filename
    else:
        # 使用URL哈希值作为文件名
        url_hash = get_url_hash(url)

        # 确定文件扩展名
        if force_extension:
            extension = force_extension
        else:
            extension = get_file_extension_from_url(url)

        # 生成文件名
        if extension:
            file_name = f"{url_hash}.{extension}"
        else:
            file_name = url_hash

    save_path = os.path.join(save_dir, file_name)

    # 如果文件已存在，直接返回
    if os.path.exists(save_path):
        logger.info(f"文件已缓存，直接返回: {save_path}")
        return save_path

    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))

        # 使用 tqdm 显示进度条
        with open(save_path, "wb") as file, tqdm(
                desc=file_name,  # 进度条描述（文件名）
                total=total_size,  # 总大小
                unit="B",  # 单位
                unit_scale=True,  # 自动缩放单位（如 KB、MB）
                unit_divisor=1024,  # 单位除数
        ) as pbar:
            for chunk in response.iter_content(chunk_size=8192):  # 增大块大小提高效率
                if chunk:
                    file.write(chunk)  # 写入文件
                    pbar.update(len(chunk))  # 更新进度条

        logger.info(f"文件下载完成: {save_path}")
        return save_path

    except requests.exceptions.RequestException as e:
        logger.error(f"下载失败: {e}")
        # 删除可能创建的不完整文件
        if os.path.exists(save_path):
            os.remove(save_path)
        raise
    except Exception as e:
        logger.error(f"下载过程中发生错误: {e}")
        if os.path.exists(save_path):
            os.remove(save_path)
        raise