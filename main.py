import os
import subprocess
import time

from selenium.webdriver.common.by import By

from config import config
from download import download_file
from log import logger
from selenium_handler import get_driver, login, access_book_pages, get_pages, access_page, auto_answer_questions

def check_ffmpeg_in_path():
    """检查系统环境变量中是否有 ffmpeg"""
    try:
        # 尝试运行 ffmpeg 命令
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

def download_ffmpeg():
    """下载 ffmpeg 并解压到工作目录的 ffmpeg 文件夹"""
    # 创建 ffmpeg 文件夹
    ffmpeg_dir = os.path.join(os.getcwd(), "ffmpeg")
    os.makedirs(ffmpeg_dir, exist_ok=True)

    # 下载 ffmpeg
    ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    ffmpeg_zip_path = download_file(ffmpeg_url, ffmpeg_dir, "ffmpeg.zip")

    # 解压 ffmpeg
    logger.info("开始解压ffmpeg...")
    import zipfile
    with zipfile.ZipFile(ffmpeg_zip_path, "r") as zip_ref:
        zip_ref.extractall(ffmpeg_dir)

    # 删除下载的压缩文件
    os.remove(ffmpeg_zip_path)
    logger.info(f"ffmpeg 已下载并解压到 {ffmpeg_dir}。")

def get_ffmpeg_bin_dir():
    """获取 ffmpeg 的 bin 目录路径"""
    # 检查系统环境变量中是否有 ffmpeg
    if check_ffmpeg_in_path():
        return None  # 如果系统环境变量中有 ffmpeg，不需要额外操作
    # 检查工作目录的 ffmpeg/bin 文件夹

    ffmpeg_bin_dir_r = os.path.join(os.getcwd(), "ffmpeg", "bin")
    if os.path.exists(ffmpeg_bin_dir_r):
        return ffmpeg_bin_dir_r

    # 如果未找到，下载 ffmpeg
    logger.info("未找到系统中的ffmpeg, 开始下载...")
    download_ffmpeg()
    return get_ffmpeg_bin_dir()  # 重新获取路径

driver = get_driver()

if __name__ == '__main__':
    ffmpeg_bin_dir = get_ffmpeg_bin_dir()

    if ffmpeg_bin_dir:
        os.environ["PATH"] += os.pathsep + ffmpeg_bin_dir

    logger.warning("请确保你有足够的流量以下载大量的音视频文件")
    logger.warning("如有支持CUDA的显卡, 请开启CUDA以加速计算能力")

    login(driver)
    access_book_pages(driver)
    pages = get_pages(driver)
    for page in pages:
        access_page(driver, page)
        auto_answer_questions(driver, page.find_element(By.CSS_SELECTOR, "span.pc-menu-node-name").text)
        time.sleep(float(config['unipus']['page_wait']))


