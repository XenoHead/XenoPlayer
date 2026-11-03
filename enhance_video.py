#!/usr/bin/env python3
"""Clean up or enlarge a video with ffmpeg filters (no AI models).

Examples:
    python enhance_video.py movie.mp4
    python enhance_video.py movie.mp4 --preset sharpen
    python enhance_video.py movie.mp4 --preset upscale --scale 2
    python enhance_video.py movie.mp4 --preset upscale --height 1440
    python enhance_video.py "D:\\Videos\\Show" --preset clean --recursive
    python enhance_video.py movie.mkv --preset upscale-clean --scale 1.5 -o out.mp4

Presets:
    clean          light denoise + deband + gentle sharpening
    sharpen        stronger sharpening, no scaling
    denoise        stronger temporal/spatial denoise
    anime          lighter denoise, stronger deband, mild sharpening
    upscale        Lanczos scaling + mild sharpening
    upscale-clean  denoise + deband + Lanczos scaling + sharpening
    none           re-encode only (still allows --scale/--width/--height)

This does not create new detail. It removes compression noise, smooths
banding, restores edge contrast, and interpolates a larger frame. A 1080p
source upscaled to 4K is still a 1080p amount of real detail.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

VIDEO_EXTS = {
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv",
    ".flv", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".3gp", ".ogv",
}

PRESETS = {
    "clean": {
        "before": ["hqdn3d=1.5:1.5:6:6", "deband=1thr=0.02:2thr=0.02:3thr=0.02"],
        "after": ["unsharp=5:5:0.5:5:5:0.0"],
    },
    "sharpen": {
        "before": [],
        "after": ["unsharp=5:5:1.0:5:5:0.0"],
    },
    "denoise": {
        "before": ["hqdn3d=2.0:2.0:8:8"],
        "after": [],
    },
    "anime": {
        "before": ["hqdn3d=1.0:1.0:4:4", "deband=1thr=0.03:2thr=0.03:3thr=0.03"],
        "after": ["unsharp=5:5:0.6:5:5:0.0"],
    },
    "upscale": {
        "before": [],
        "after": ["unsharp=5:5:0.7:5:5:0.0"],
    },
    "upscale-clean": {
        "before": ["hqdn3d=1.5:1.5:6:6", "deband=1thr=0.02:2thr=0.02:3thr=0.02"],
        "after": ["unsharp=5:5:0.7:5:5:0.0"],
    },
    "none": {"before": [], "after": []},
}


def find_tool(name, override=""):
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    exe = name + ".exe" if os.name == "nt" else name
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), exe),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg", "bin", exe),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg", exe),
    ]
    if os.name == "nt":
        candidates += [
            r"C:\ffmpeg\bin\ffmpeg.exe" if name == "ffmpeg" else r"C:\ffmpeg\bin\ffprobe.exe",
            r"D:\Tools\ffmpeg\bin\ffmpeg.exe" if name == "ffmpeg" else r"D:\Tools\ffmpeg\bin\ffprobe.exe",
        ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


def probe_duration(ffprobe, path):
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        data = json.loads(result.stdout or "{}")
        return float(data.get("format", {}).get("duration") or 0)
    except Exception:
        return 0.0


def probe_size(ffprobe, path):
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "json", str(path),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        streams = json.loads(result.stdout or "{}").get("streams") or [{}]
        return int(streams[0].get("width") or 0), int(streams[0].get("height") or 0)
    except Exception:
        return 0, 0


def scale_filter(scale, width, height):
    if height:
        return f"scale=-2:{height}:flags=lanczos"
    if width:
        return f"scale={width}:-2:flags=lanczos"
    if scale and scale != 1.0:
        return (
            f"scale=trunc(iw*{scale}/2)*2:"
            f"trunc(ih*{scale}/2)*2:flags=lanczos"
        )
    return ""


def build_filter_chain(preset, scale=1.0, width=None, height=None, deinterlace=False):
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}")
    chain = []
    if deinterlace:
        chain.append("yadif=deint=interlaced")
    chain.extend(PRESETS[preset]["before"])
    scaling = scale_filter(scale, width, height)
    if scaling:
        chain.append(scaling)
    chain.extend(PRESETS[preset]["after"])
    return ",".join(chain)


def build_filters(args):
    return build_filter_chain(
        args.preset, args.scale, args.width, args.height, args.deinterlace
    )


def default_output(source, output_dir=None, suffix="_enhanced", overwrite=False):
    source = Path(source)
    folder = Path(output_dir) if output_dir else source.parent
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (source.stem + suffix + ".mp4")
    if not overwrite:
        index = 2
        while target.exists():
            target = folder / (source.stem + suffix + f"_{index}.mp4")
            index += 1
    return target


def iter_sources(path, recursive):
    path = Path(path)
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise SystemExit(f"Not found: {path}")
    pattern = "**/*" if recursive else "*"
    return sorted(
        item for item in path.glob(pattern)
        if item.is_file() and item.suffix.lower() in VIDEO_EXTS
    )


def run_one(args, source, ffmpeg, ffprobe):
    source = Path(source)
    if source.suffix.lower() not in VIDEO_EXTS:
        print(f"Skipping unsupported file: {source}")
        return 0

    if args.output and len(iter_sources(args.input, args.recursive)) == 1:
        target = Path(args.output)
    else:
        target = default_output(
            source, args.output_dir, args.suffix, args.overwrite
        )

    if target.resolve() == source.resolve():
        print(f"Refusing to overwrite the input file: {source}")
        return 1
    if target.exists() and not args.overwrite:
        print(f"Skipping existing output: {target}")
        return 0

    filters = build_filters(args)
    width, height = probe_size(ffprobe, source)
    duration = probe_duration(ffprobe, source)

    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0",
        "-c:v", "libx264", "-preset", args.speed, "-crf", str(args.crf),
        "-pix_fmt", "yuv420p",
    ]
    if filters:
        cmd += ["-vf", filters]
    if args.copy_audio:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    if target.suffix.lower() in (".mp4", ".m4v", ".mov"):
        cmd += ["-movflags", "+faststart"]
    cmd += ["-progress", "pipe:1", "-nostats", str(target)]

    print(f"\n{source}")
    if width and height:
        print(f"  input : {width}x{height}")
    if filters:
        print(f"  filter: {filters}")
    print(f"  output: {target}  (CRF {args.crf}, {args.speed})")
    if args.dry_run:
        print("  " + " ".join(cmd))
        return 0

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    last_error = ""
    started = time.time()
    for line in process.stdout:
        line = line.strip()
        if line.startswith(("out_time_us=", "out_time_ms=")):
            try:
                seconds = int(line.split("=", 1)[1]) / 1_000_000.0
                if duration > 0:
                    percent = min(99, max(0, int(seconds / duration * 100)))
                    elapsed = max(0.1, time.time() - started)
                    eta = elapsed * (100 - percent) / max(1, percent)
                    sys.stdout.write(
                        f"\r  progress: {percent:3d}%  ETA {int(eta // 60):02d}:{int(eta % 60):02d}"
                    )
                    sys.stdout.flush()
            except Exception:
                pass
        elif line and "=" not in line:
            last_error = line
    process.wait()
    sys.stdout.write("\r" + " " * 60 + "\r")
    if process.returncode != 0:
        print(f"  failed (exit {process.returncode}): {last_error or 'ffmpeg error'}")
        return process.returncode

    new_w, new_h = probe_size(ffprobe, target)
    print(f"  done  : {new_w}x{new_h}  {time.time() - started:.1f}s")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Clean up or upscale video with ffmpeg filters (no AI).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Video file or folder")
    parser.add_argument("-o", "--output", help="Output file (single input only)")
    parser.add_argument("--output-dir", help="Folder for batch output")
    parser.add_argument("--suffix", default="_enhanced", help="Batch filename suffix")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="clean")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="Scale factor, e.g. 2 for 2x (default: 1)")
    parser.add_argument("--width", type=int, help="Target width (keeps aspect)")
    parser.add_argument("--height", type=int, help="Target height (keeps aspect)")
    parser.add_argument("--crf", type=int, default=18,
                        help="x264 quality, lower is better/larger (default: 18)")
    parser.add_argument("--speed", default="medium",
                        choices=["ultrafast", "superfast", "veryfast", "faster",
                                 "fast", "medium", "slow", "slower", "veryslow"],
                        help="x264 speed preset (default: medium)")
    parser.add_argument("--copy-audio", action="store_true",
                        help="Copy the original audio instead of re-encoding to AAC")
    parser.add_argument("--deinterlace", action="store_true",
                        help="Apply yadif deinterlacing (DVD/TV sources)")
    parser.add_argument("--recursive", action="store_true",
                        help="Process subfolders when input is a folder")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite an existing output file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the ffmpeg command without running it")
    parser.add_argument("--ffmpeg", default="", help="Path to ffmpeg")
    parser.add_argument("--ffprobe", default="", help="Path to ffprobe")
    args = parser.parse_args()

    if args.width and args.height:
        parser.error("Use --width or --height, not both.")
    if args.scale and args.scale <= 0:
        parser.error("--scale must be greater than 0.")
    if args.width and args.width <= 0:
        parser.error("--width must be greater than 0.")
    if args.height and args.height <= 0:
        parser.error("--height must be greater than 0.")

    ffmpeg = find_tool("ffmpeg", args.ffmpeg)
    ffprobe = find_tool("ffprobe", args.ffprobe)
    if not ffmpeg:
        raise SystemExit("ffmpeg not found. Install it or pass --ffmpeg PATH.")
    if not ffprobe:
        raise SystemExit("ffprobe not found. Install it or pass --ffprobe PATH.")

    sources = iter_sources(args.input, args.recursive)
    if not sources:
        raise SystemExit(f"No supported video files found in {args.input}.")
    if args.output and len(sources) > 1:
        raise SystemExit("--output only works with a single input file.")

    print(f"Using ffmpeg: {ffmpeg}")
    if args.preset == "upscale" and args.scale == 1.0 and not (args.width or args.height):
        print("Note: --preset upscale without --scale/--width/--height only sharpens.")
    if args.scale > 2:
        print("Note: more than 2x is slow and adds no real detail.")

    failures = 0
    for index, source in enumerate(sources, 1):
        if len(sources) > 1:
            print(f"\n[{index}/{len(sources)}]")
        failures += 1 if run_one(args, source, ffmpeg, ffprobe) else 0

    if len(sources) > 1:
        print(f"\nFinished: {len(sources) - failures} succeeded, {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
