# -*- coding: utf-8 -*-
"""
novel2comic/core/audio_utils.py

纯 stdlib 的 wav 拼接工具，避免 pydub（Python 3.13 无 audioop）。
支持 mp3→wav 转换（通过 ffmpeg）。
"""

from __future__ import annotations

import subprocess
import tempfile
import wave
from io import BytesIO
from pathlib import Path
from typing import List


def _ensure_wav(audio_bytes: bytes) -> bytes:
	"""
	若为 mp3/其他格式，用 ffmpeg 转为 wav。若已是 wav 则原样返回。
	"""
	if audio_bytes[:4] == b"RIFF":
		return audio_bytes
	# mp3/opus 等需转换
	with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fin:
		fin.write(audio_bytes)
		mp3_path = fin.name
	wav_path = None
	try:
		with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fout:
			wav_path = fout.name
		subprocess.run(
			["ffmpeg", "-y", "-i", mp3_path, "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1", wav_path],
			check=True,
			capture_output=True,
		)
		return Path(wav_path).read_bytes()
	finally:
		Path(mp3_path).unlink(missing_ok=True)
		if wav_path:
			Path(wav_path).unlink(missing_ok=True)


def wav_duration_ms(wav_bytes: bytes) -> int:
	"""从 wav bytes 获取时长（ms）。"""
	with wave.open(BytesIO(wav_bytes), "rb") as wf:
		frames = wf.getnframes()
		rate = wf.getframerate()
		return int(frames / rate * 1000)


def create_silence_ms(ms: int, sample_rate: int = 24000, nchannels: int = 1, sampwidth: int = 2) -> bytes:
	"""生成静音 wav bytes。"""
	buf = BytesIO()
	with wave.open(buf, "wb") as wf:
		wf.setnchannels(nchannels)
		wf.setsampwidth(sampwidth)
		wf.setframerate(sample_rate)
		n_frames = int(sample_rate * ms / 1000)
		wf.writeframes(b"\x00" * (n_frames * nchannels * sampwidth))
	return buf.getvalue()


def concat_wavs(wav_list: List[bytes], silence_between_ms: int = 0, sample_rate: int = 24000) -> bytes:
	"""
	拼接多个 wav。中间可插静音。
	要求所有 wav 格式一致（mono, 16bit）。
	"""
	if not wav_list:
		return b""
	pauses = [silence_between_ms] * (len(wav_list) - 1) if silence_between_ms > 0 else []
	return concat_wavs_with_pauses(wav_list, pauses, sample_rate)


def concat_wavs_with_pauses(
	wav_list: List[bytes],
	pauses_after: List[int],
	sample_rate: int = 24000,
) -> bytes:
	"""
	拼接多个 wav，每段之间插入指定时长的静音。
	pauses_after[i] = 在 wav_list[i] 与 wav_list[i+1] 之间的静音（ms）。
	len(pauses_after) 应为 len(wav_list)-1；不足则补 0。
	不修改传入的 pauses_after。
	"""
	if not wav_list:
		return b""
	pauses = list(pauses_after)
	while len(pauses) < len(wav_list) - 1:
		pauses.append(0)

	params = None
	all_frames = []

	for i, wav_bytes in enumerate(wav_list):
		with wave.open(BytesIO(wav_bytes), "rb") as wf:
			p = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate())
			if params is None:
				params = p
			elif p != params:
				raise ValueError(f"incompatible wav format: {p} vs {params}")
			all_frames.append(wf.readframes(wf.getnframes()))

		if i < len(pauses) and pauses[i] > 0:
			silence = create_silence_ms(pauses[i], params[2], params[0], params[1])
			with wave.open(BytesIO(silence), "rb") as wf:
				all_frames.append(wf.readframes(wf.getnframes()))

	buf = BytesIO()
	with wave.open(buf, "wb") as wf:
		wf.setnchannels(params[0])
		wf.setsampwidth(params[1])
		wf.setframerate(params[2])
		wf.writeframes(b"".join(all_frames))
	return buf.getvalue()
