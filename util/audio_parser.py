import torch
import whisper
import os
from moviepy import VideoFileClip

from util.log import logger

path_to_video_cache = {}
path_to_audio_cache = {}


def from_video(video_path: str) -> str:
    if video_path in path_to_video_cache:
        logger.info(f"使用视频缓存: {video_path}")
        return path_to_video_cache[video_path]

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    video = None

    try:
        audio_path = f"{os.path.splitext(video_path)[0]}.mp3"

        if not os.path.exists(audio_path):
            logger.info(f"正在从视频提取音频: {video_path}")
            video = VideoFileClip(video_path)

            if video.audio is None:
                raise ValueError(f"视频文件没有音频轨道: {video_path}")

            video.audio.write_audiofile(audio_path, logger=None)
        text = from_audio(audio_path)
        path_to_video_cache[video_path] = text
        logger.info(f"视频转录完成: {video_path}")

        return text

    except Exception as e:
        logger.error(f"视频转录失败 {video_path}: {e}")
        raise
    finally:
        if video is not None:
            video.close()


def from_audio(audio_path: str, language_t: str = "en") -> str:
    cache_key = f"{audio_path}_{language_t}"
    if cache_key in path_to_audio_cache:
        logger.info(f"使用音频缓存: {audio_path}")
        return path_to_audio_cache[cache_key]

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = load_whisper_model(device)

        fp16 = device == "cuda"

        logger.info(f"开始转录音频: {audio_path}, 语言: {language_t}")
        result = model.transcribe(
            audio_path,
            language=language_t if language_t != "auto" else None,
            fp16=fp16,
            verbose=False
        )

        text = result["text"].strip()

        path_to_audio_cache[cache_key] = text
        logger.info(f"音频转录完成: {audio_path}, 文本长度: {len(text)}")

        return text

    except Exception as e:
        logger.error(f"音频转录失败 {audio_path}: {e}")
        raise


_whisper_model_cache = {}


def load_whisper_model(device: str, model_size: str = "base"):
    cache_key = f"{model_size}_{device}"

    if cache_key not in _whisper_model_cache:
        logger.info(f"加载Whisper模型: {model_size} on {device}")

        model_dir = "./models"
        os.makedirs(model_dir, exist_ok=True)

        model = whisper.load_model(model_size, download_root=model_dir)
        model = model.to(device)

        _whisper_model_cache[cache_key] = model
        logger.info(f"模型加载完成: {model_size}")
    return _whisper_model_cache[cache_key]