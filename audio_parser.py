import torch
import whisper
from moviepy import VideoFileClip

import download
from log import logger

path_to_video_cache = {}
path_to_audio_cache = {}

def from_video(video_path) -> str:
    if video_path in path_to_video_cache:
        return path_to_video_cache[video_path]
    audio_path = download.using_cached_file("mp3")
    video = VideoFileClip(video_path)
    video.audio.write_audiofile(audio_path)
    text = from_audio(audio_path)
    path_to_video_cache[video_path] = text
    return text

def from_audio(audio_path, language_t="en") -> str:
    if audio_path in path_to_audio_cache:
        return path_to_audio_cache[audio_path]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {device}")
    model = whisper.load_model("base").to(device)
    fp16 = device == "cuda"
    result = model.transcribe(audio_path, language=language_t, fp16=fp16)
    text = result["text"]
    path_to_audio_cache[audio_path] = text
    return text