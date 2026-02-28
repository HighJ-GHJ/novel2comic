# -*- coding: utf-8 -*-
"""
novel2comic/stages/render.py

Render 阶段：占位图 + chapter.wav + chapter.ass -> video/preview.mp4
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from novel2comic.core.io import ChapterPaths
from novel2comic.core.manifest import load_manifest, save_manifest


class RenderStage:
	name = "render"

	def run(self, paths: ChapterPaths, ctx: object) -> None:
		if not paths.audio_chapter_wav.exists():
			raise FileNotFoundError(f"missing {paths.audio_chapter_wav}")
		if not paths.subtitles_ass.exists():
			raise FileNotFoundError(f"missing {paths.subtitles_ass}")

		m = load_manifest(paths.manifest)
		if m.stage not in ("aligned", "rendered"):
			raise ValueError(f"Render requires aligned, got {m.stage}")

		paths.video_dir.mkdir(parents=True, exist_ok=True)

		# 从 manifest 或 wav 获取时长
		audio_ms = m.durations.get("audio_ms", 0)
		if audio_ms <= 0:
			import wave
			with wave.open(str(paths.audio_chapter_wav), "rb") as wf:
				frames = wf.getnframes()
				rate = wf.getframerate()
				audio_ms = int(frames / rate * 1000)
		duration_sec = audio_ms / 1000.0

		# ffmpeg: 纯色背景 + 音频 + ASS 字幕
		# -f lavfi -i color=... 生成纯色视频
		# -i chapter.wav 音频
		# -vf ass=... 烧录字幕
		ass_path = paths.subtitles_ass.resolve()
		cmd = [
			"ffmpeg", "-y",
			"-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1920x1080:d={duration_sec}",
			"-i", str(paths.audio_chapter_wav),
			"-vf", f"ass={ass_path}",
			"-c:v", "libx264", "-preset", "fast", "-crf", "23",
			"-c:a", "aac", "-b:a", "128k",
			"-shortest",
			str(paths.video_preview_mp4),
		]
		r = subprocess.run(cmd, capture_output=True, text=True)
		if r.returncode != 0:
			raise RuntimeError(f"ffmpeg failed: {r.stderr[:1000]}")

		m.durations["video_ms"] = audio_ms
		m.set_stage("rendered")
		m.mark_done("render")
		save_manifest(paths.manifest, m)
