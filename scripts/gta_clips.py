"""Gorizontal (16:9) videodan vertikal Shorts bo'laklarini kesadi.

Ishlatish:
    python scripts/gta_clips.py clips.json out_dir

clips.json: [{"id": "01_x", "src": "video.mp4", "start": 2.0, "end": 25.7,
              "top": "SARLAVHA", "bottom": "19-NOYABR"}, ...]
Kadr: xira fon ustida 1.6x kattalashtirilgan markaziy qism, tepada sarlavha, pastda yozuv.
Asl ovoz saqlanadi (-14 LUFS).
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FONT = Path(__file__).resolve().parent.parent / "cartoon" / "fonts" / "Anton-Regular.ttf"
W, H, FG_H = 1080, 1920, 880  # FG_H: old kadr balandligi (kattalashtiriladi, yonlari kesiladi)


def text(tmp: Path, name: str, value: str, size: int, y: int, color: str, up: bool) -> str:
    """Har bir qator alohida chiziladi (markazga tekislash uchun). up=True: y dan tepaga qarab."""
    lines = [ln for ln in value.split("\n") if ln]
    step = int(size * 1.25)
    parts = []
    for i, ln in enumerate(lines):
        f = tmp / f"{name}{i}.txt"
        f.write_text(ln, encoding="utf-8")
        ly = y - step * (len(lines) - i) if up else y + step * i
        parts.append(f"drawtext=fontfile='{FONT}':textfile='{f}':fontsize={size}:fontcolor={color}:"
                     f"borderw=6:bordercolor=black:x=(w-text_w)/2:y={ly}")
    return ",".join(parts) if parts else "null"


def letterbox(src: Path, at: float) -> str:
    """Qora hoshiyalarni aniqlaydi (kinoformat treylerlar uchun). Natija: crop=w:h:x:y."""
    r = subprocess.run(["ffmpeg", "-ss", str(at), "-t", "4", "-i", str(src), "-vf", "cropdetect=24:2:0",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    found = re.findall(r"crop=(\d+:\d+:\d+:\d+)", r.stderr)
    return "crop=" + found[-1] if found else "null"


def render(clip: dict, src_dir: Path, out_dir: Path) -> Path:
    out = out_dir / f"{clip['id']}.mp4"
    dur = clip["end"] - clip["start"]
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        top_y = (H - FG_H) // 2
        vf = (
            f"[0:v]{letterbox(src_dir / clip['src'], clip['start'] + dur / 2)},split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=40:5,eq=brightness=-0.3[bg];"
            f"[b]scale=-2:{FG_H},crop={W}:{FG_H}[fg];"
            f"[bg][fg]overlay=0:{top_y}[v0];"
            f"[v0]{text(tmp, 'top', clip['top'], 100, top_y - 60, 'white', True)},"
            f"{text(tmp, 'bot', clip.get('bottom', ''), 80, top_y + FG_H + 70, '0xFF4FD8', False)},"
            f"fade=t=in:d=0.25,fade=t=out:st={dur - 0.3:.2f}:d=0.3[v]"
        )
        af = f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:d=0.2,afade=t=out:st={dur - 0.3:.2f}:d=0.3"
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-ss", str(clip["start"]), "-t", f"{dur:.3f}",
            "-i", str(src_dir / clip["src"]), "-filter_complex", vf, "-map", "[v]", "-map", "0:a",
            "-af", af, "-r", "30", "-c:v", "libx264", "-crf", "19", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", str(out),
        ], check=True)
    return out


def main() -> None:
    spec, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    for clip in json.loads(spec.read_text(encoding="utf-8")):
        print(render(clip, spec.parent, out_dir))


if __name__ == "__main__":
    main()
