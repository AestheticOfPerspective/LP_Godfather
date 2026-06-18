"""
Video Pipeline — OpenMontage Integration Layer

Cherry-picked video analysis tools with OpenMontage backend or standalone fallback.
Returns JSON for LLM consumption (scene detection, transcription, frames, subtitles).

Usage:
    python video_pipeline.py scene-detect --input video.mp4
    python video_pipeline.py transcribe --input video.mp4
    python video_pipeline.py analyze --input video.mp4
    python video_pipeline.py subtitles --input video.mp4
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

try:
    from tools.tool_registry import registry
    registry.discover()
    HAS_OPENMONTAGE = True
except ImportError:
    HAS_OPENMONTAGE = False


def check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def ffprobe(input_path: str) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_path],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


# =====================================
# SCENE DETECTION
# =====================================

def scene_detect(input_path: str, threshold: float = 30.0) -> list[dict[str, Any]]:
    if HAS_OPENMONTAGE:
        try:
            tool = registry.get_by_capability("scene_detection")[0]
            result = tool.execute({"input_path": input_path, "threshold": threshold})
            return result.data
        except Exception:
            pass

    if not check_ffmpeg():
        return [{"error": "FFmpeg not found. Install ffmpeg or OpenMontage."}]

    probe = ffprobe(input_path)
    duration = float(probe.get("format", {}).get("duration", 0))

    result = subprocess.run(
        ["ffmpeg", "-i", input_path, "-filter:v", f"select='gt(scene,{threshold/100})',showinfo",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    scenes = []
    for line in result.stderr.split("\n"):
        if "pts_time:" in line:
            try:
                pts = float(line.split("pts_time:")[1].split()[0])
                scenes.append({"scene": len(scenes) + 1, "start": pts, "end": 0.0})
            except (ValueError, IndexError):
                pass

    for i in range(len(scenes) - 1):
        scenes[i]["end"] = scenes[i + 1]["start"]
    if scenes:
        scenes[-1]["end"] = duration

    return scenes or [{"scene": 1, "start": 0.0, "end": duration, "note": "No scene changes detected"}]


# =====================================
# TRANSCRIPTION (WhisperX / faster-whisper)
# =====================================

def transcribe(input_path: str, model_size: str = "base") -> dict[str, Any]:
    if HAS_OPENMONTAGE:
        try:
            tool = registry.get_by_capability("transcribe")[0]
            result = tool.execute({"input_path": input_path, "model_size": model_size})
            return {"segments": result.data, "format": "whisperx"}
        except Exception:
            pass

    try:
        import whisper
        try:
            model = whisper.load_model(model_size)
        except Exception:
            model = whisper.load_model(model_size, device="cpu")
        result = model.transcribe(input_path)
        segments = []
        for seg in result["segments"]:
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            })
        return {"segments": segments, "language": result.get("language", "unknown"), "format": "whisper"}
    except ImportError:
        return {"error": "openai-whisper not installed. pip install openai-whisper"}
    except Exception as e:
        return {"error": f"Transcription failed: {e}"}


# =====================================
# FRAME SAMPLING
# =====================================

def sample_frames(input_path: str, interval: float = 10.0, output_dir: Optional[str] = None) -> list[str]:
    if HAS_OPENMONTAGE:
        try:
            tool = registry.get_by_capability("frame_extraction")[0]
            result = tool.execute({"input_path": input_path, "interval": interval})
            return result.data
        except Exception:
            pass

    if not check_ffmpeg():
        return []

    probe = ffprobe(input_path)
    duration = float(probe.get("format", {}).get("duration", 0))
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="frames_")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    frames = []
    t = 0.0
    while t < duration:
        fname = f"frame_{t:06.2f}.jpg"
        fpath = str(out_path / fname)
        subprocess.run(
            ["ffmpeg", "-ss", str(t), "-i", input_path, "-vframes", "1", "-q:v", "2", fpath, "-y"],
            capture_output=True,
        )
        frames.append(fpath)
        t += interval

    return frames


# =====================================
# SUBTITLE GENERATION
# =====================================

def generate_subtitles(input_path: str, format: str = "srt") -> str:
    if HAS_OPENMONTAGE:
        try:
            tool = registry.get_by_capability("subtitle_generation")[0]
            result = tool.execute({"input_path": input_path, "format": format})
            return result.data
        except Exception:
            pass

    result = transcribe(input_path)
    if "error" in result:
        return f"Error: {result['error']}"

    segments = result.get("segments", [])
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _fmt_time(seg["start"])
        end = _fmt_time(seg["end"])
        text = seg.get("text", "")
        if format == "srt":
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        elif format == "vtt":
            lines.append(f"{start} --> {end}\n{text}\n")

    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# =====================================
# FULL ANALYSIS (scene + transcribe + frames)
# =====================================

def analyze_video(input_path: str) -> dict[str, Any]:
    info = ffprobe(input_path) if check_ffmpeg() else {}
    scenes = scene_detect(input_path)
    transcript = transcribe(input_path)

    highlight_script = None
    if "segments" in transcript:
        segs = transcript["segments"]
        scene_text = "\n".join(f"[{s['start']:.1f}s-{s['end']:.1f}s] {s['text']}" for s in segs[:10])
        highlight_script = (
            f"Analyzed {input_path}. Scenes: {len(scenes)}, "
            f"Transcript segments: {len(segs)}. "
            f"First segments:\n{scene_text}\n\n"
            f"Use this data to identify highlights."
        )

    return {
        "file": input_path,
        "format": info.get("format", {}),
        "streams": info.get("streams", []),
        "scenes": scenes,
        "transcript": transcript,
        "processing": {
            "openmontage_available": HAS_OPENMONTAGE,
            "ffmpeg_available": check_ffmpeg(),
        },
        "agent_summary": highlight_script,
    }


# =====================================
# CLI
# =====================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    kwargs = {}
    for i in range(2, len(sys.argv), 2):
        if i + 1 < len(sys.argv):
            key = sys.argv[i].lstrip("--").replace("-", "_")
            val = sys.argv[i + 1]
            kwargs[key] = val

    input_path = kwargs.get("input")
    if not input_path and command not in ("help", "status"):
        print("Error: --input required")
        sys.exit(1)

    if command == "scene-detect":
        result = scene_detect(input_path, float(kwargs.get("threshold", 30)))
    elif command == "transcribe":
        result = transcribe(input_path, kwargs.get("model", "base"))
    elif command == "frames":
        result = sample_frames(input_path, float(kwargs.get("interval", 10)), kwargs.get("output"))
    elif command == "subtitles":
        result = generate_subtitles(input_path, kwargs.get("format", "srt"))
    elif command == "analyze":
        result = analyze_video(input_path)
    elif command == "status":
        result = {
            "openmontage": HAS_OPENMONTAGE,
            "ffmpeg": check_ffmpeg(),
        }
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
