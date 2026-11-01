"""Premium harakat dizayni: ovoz effektlari (sintez), hook kirishi, tekstura, oxirgi zoom.

Hammasi ffmpeg lavfi / PIL bilan hosil qilinadi (yuklab olingan fayl yo'q). Har bir effekt nozik
bo'lishi kerak va render.py da xato bo'lsa oddiy renderga qaytiladi.
"""
from pathlib import Path

import numpy as np
from PIL import Image

from .utils import log, run

SR = 48000
PUNCH_ZOOM, PUNCH_SECS = 0.07, 0.5      # birinchi sahna: 1.07x dan 1.0x ga
END_ZOOM, END_SECS = 0.06, 1.2          # oxirgi 1.2 soniya
FLASH_SECS, BLUR_SECS = 0.30, 0.45
LEAK_SECS, LEAK_ALPHA, MAX_LEAKS = 0.9, 0.2, 5

# SFX cho'qqisi ovoz cho'qqisidan shuncha dB past (ovoz doim ustun)
GAIN_DB = {"whoosh": -15.0, "hit": -11.0, "riser": -17.0}
MAX_SFX_EVENTS = 12


# ---------- ovoz ----------
def _peak_db(path: Path, default: float = -3.0) -> float:
    res = run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"])
    for line in res.stderr.splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:")[1].split("dB")[0])
            except ValueError:
                break
    return default


def _synth(path: Path, graph: str, src: str) -> None:
    run(["ffmpeg", "-y", "-hide_banner", "-f", "lavfi", "-i", src, "-af", graph,
         "-ar", str(SR), "-ac", "1", str(path)])


def _normalize(raw: Path, out: Path) -> None:
    """Cho'qqisini 0 dBFS ga keltiradi (keyin aniq dB bilan pasaytiriladi)."""
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(raw), "-af",
         f"volume={-_peak_db(raw):.2f}dB", "-ar", str(SR), str(out)])


def _base_sounds(wd: Path) -> dict[str, Path]:
    raw = {
        # past shovqin so'nib, yuqori shovqin kuchayadi: yumshoq "havo" o'tishi
        "whoosh": (
            "anoisesrc=d=0.8:c=pink:a=0.9:r=48000",
            ("asplit[n1][n2];"
             "[n1]lowpass=f=1300,afade=t=in:d=0.3:curve=qsin,afade=t=out:st=0.3:d=0.3:curve=qsin[lo];"
             "[n2]highpass=f=2000,lowpass=f=9000,afade=t=in:st=0.15:d=0.3:curve=qsin,"
             "afade=t=out:st=0.45:d=0.35:curve=qsin[hi];"
             "[lo][hi]amix=inputs=2:normalize=0,lowpass=f=8000,volume=2")),
        # past "dum" + qisqa pastga tushuvchi chastota
        "hit": (
            "aevalsrc='sin(2*PI*(48*t+(95/26)*(1-exp(-26*t))))*exp(-t*6.5)':d=0.8:s=48000",
            "afade=t=in:d=0.004,lowpass=f=420"),
        # sekin kuchayuvchi shovqin (hook ostida)
        "riser": (
            "anoisesrc=d=1.0:c=pink:a=0.9:r=48000",
            "highpass=f=1200,lowpass=f=7000,afade=t=in:d=0.95:curve=exp,afade=t=out:st=0.9:d=0.1"),
    }
    out = {}
    for name, (src, graph) in raw.items():
        r = wd / f"sfx_{name}_raw.wav"
        _synth(r, graph, src)
        out[name] = wd / f"sfx_{name}.wav"
        _normalize(r, out[name])
    return out


def sfx_events(kind: str, centers: list[float], hook_secs: float) -> list[tuple[float, str]]:
    """(boshlanish vaqti, tovush) ro'yxati. centers = o'tish markazlari (s)."""
    ev: list[tuple[float, str]] = []
    if kind in ("whoosh_hit", "whoosh_riser", "whoosh"):
        ev += [(max(c - 0.32, 0.0), "whoosh") for c in centers]
    if kind in ("whoosh_hit", "hit"):
        ev.append((0.0, "hit"))
    if kind == "whoosh_riser":
        ev.append((0.0, "riser"))
        ev.append((min(0.95, max(hook_secs - 0.6, 0.3)), "hit"))
    return sorted(ev)[:MAX_SFX_EVENTS]


def build_sfx(wd: Path, total: float, events: list[tuple[float, str]], voice: Path) -> Path | None:
    """Barcha effektlarni bitta yo'lga yig'adi; cho'qqi = ovoz cho'qqisi - GAIN_DB."""
    if not events:
        return None
    base = _base_sounds(wd)
    voice_peak = _peak_db(voice)
    inputs, parts, labels = [], [], []
    for i, (t, name) in enumerate(events):
        inputs += ["-i", str(base[name])]
        gain = voice_peak + GAIN_DB[name]
        parts.append(f"[{i}:a]volume={gain:.2f}dB,adelay={int(t * 1000)}:all=1[e{i}]")
        labels.append(f"[e{i}]")
    graph = (";".join(parts) + ";" + "".join(labels) +
             f"amix=inputs={len(labels)}:normalize=0:duration=longest,"
             f"apad=whole_dur={total:.3f},atrim=0:{total:.3f}[s]")
    out = wd / "sfx.wav"
    run(["ffmpeg", "-y", "-hide_banner", *inputs, "-filter_complex", graph,
         "-map", "[s]", "-ar", str(SR), "-ac", "1", str(out)])
    return out


# ---------- video ----------
def _leak_png(path: Path, w: int = 1500, h: int = 1920) -> Path:
    """Issiq, yumshoq, qiya yorug'lik yo'li (RGBA)."""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    d = (xs + 0.28 * ys - 0.5 * w - 0.14 * h) / (0.3 * w)
    a = np.exp(-d * d) * LEAK_ALPHA
    core = np.exp(-(d * 1.8) ** 2)
    rgb = np.zeros((h, w, 3), np.float32)
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = 255, 185 + 50 * core, 120 + 100 * core
    img = np.dstack([rgb, a * 255]).clip(0, 255).astype(np.uint8)
    Image.fromarray(img, "RGBA").save(path)
    return path


def zoom_expr(entrance: str, ending: bool, total: float) -> str | None:
    terms = []
    if entrance in ("punch",):
        terms.append(f"{PUNCH_ZOOM}*pow(max(0,1-t/{PUNCH_SECS}),2)")
    if ending:
        terms.append(f"{END_ZOOM}*pow(clip((t-{total - END_SECS:.3f})/{END_SECS},0,1),2)")
    return "+".join(terms) or None


def video_fx(look: dict, total: float, centers: list[float], wd: Path, W: int, H: int,
             first_extra_input: int, ending: bool) -> tuple[list[str], str, str]:
    """(qo'shimcha kirishlar, filtr zanjiri [0:v] dan [fxv] gacha, ...). Bo'sh bo'lsa zanjir ''."""
    entrance = look.get("entrance", "")
    texture = look.get("texture", "")
    steps: list[str] = []
    z = zoom_expr(entrance, ending, total)
    if z:
        steps.append(f"scale=w='trunc(iw*(1+{z})/2)*2':h='trunc(ih*(1+{z})/2)*2':eval=frame:flags=bicubic,"
                     f"crop={W}:{H}")
    if entrance == "flash":
        k = f"max(0,1-t/{FLASH_SECS})"
        steps.append(f"eq=brightness='0.16*pow({k},2)':contrast='1+0.12*{k}':eval=frame")
    if "grain" in texture:
        steps.append("noise=alls=5:allf=t")
    pre = ",".join(steps)

    graph, inputs = [], []
    cur = "[0:v]"
    if pre:
        graph.append(f"{cur}{pre}[f1]")
        cur = "[f1]"
    if entrance == "blur":
        graph.append(f"{cur}split[bs][bb];[bb]trim=duration={BLUR_SECS},setpts=PTS-STARTPTS,gblur=sigma=16:steps=2,format=yuva420p,"
                     f"fade=t=out:st=0:d={BLUR_SECS}:alpha=1[bbl];[bs][bbl]overlay=format=auto[f2]")
        cur = "[f2]"
    idx = first_extra_input
    if texture == "breathe":
        # vignette=eval=frame juda sekin; o'rniga kichik (135x240) alfa maskasi hosil qilib kattalashtiramiz
        inputs += ["-f", "lavfi", "-i", f"color=c=black:s=135x240:r=30:d={total:.2f}"]
        graph.append(
            f"[{idx}:v]format=yuva420p,geq=lum='0':cb=128:cr=128:a='255*clip(pow(hypot(X/W-0.5,Y/H-0.5)/0.6,2.2),0,1)"
            f"*(0.34+0.1*sin(2*PI*T/4.5))',scale={W}:{H}:flags=bilinear[vg]")
        graph.append(f"{cur}[vg]overlay=format=auto[vgo]")
        cur = "[vgo]"
        idx += 1
    leaks = [c for c in centers if c < total - 0.5][:MAX_LEAKS] if "leak" in texture else []
    if leaks:
        inputs += ["-framerate", "30", "-i", str(_leak_png(wd / "leak.png"))]
        labels = "".join(f"[lk{i}]" for i in range(len(leaks)))
        # bitta kadrni yuva420p ga bir marta o'giramiz va takrorlaymiz (har kadrda PNG o'qish juda sekin)
        prep = f"[{idx}:v]format=yuva420p,loop=loop=-1:size=1:start=0,setpts=N/30/TB"
        graph.append(f"{prep},split={len(leaks)}{labels}" if len(leaks) > 1 else f"{prep}[lk0]")
        for i, c in enumerate(leaks):
            t0 = c - LEAK_SECS / 2
            graph.append(
                f"{cur}[lk{i}]overlay=x='-w+(W+w)*(t-{t0:.3f})/{LEAK_SECS}':y=0:eval=frame:"
                f"enable='between(t,{t0:.3f},{t0 + LEAK_SECS:.3f})':format=auto[l{i}]")
            cur = f"[l{i}]"
    if not graph:
        return [], "", "[0:v]"
    graph.append(f"{cur}null[fxv]")
    return inputs, ";".join(graph), "[fxv]"


def log_fx(look: dict) -> None:
    log.info("FX: sound=%s entrance=%s texture=%s emphasis=%s ending=%s", look.get("sound"),
             look.get("entrance"), look.get("texture"), look.get("emphasis"), look.get("ending"))
