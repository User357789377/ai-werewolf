# -*- coding: utf-8 -*-
"""
给对局记录配音：每句要念出来的话生成一个音频文件，记下时长，给 render.py 用。

用法：
  python tts.py out/某局/log.json            # 上帝视角的记录
  python tts.py out/某局/log_pov5.json       # 某个视角导出的记录（用法一样）
依赖：pip install edge-tts imageio-ffmpeg
输出：和 log 同目录的 audio/ 文件夹（每句一个 mp3）和 audio/timing.json（每句时长）。
已经生成过的句子会跳过，中断后重跑会接着做。
"""
import argparse
import asyncio
import json
import os
import sys

JUDGE_VOICE = "zh-CN-YunyangNeural"   # 法官：新闻播音腔
# 这些类型的事件要念出来；狼人夜聊是打字，不配音
VOICED = {"judge", "speech", "last_words", "pk_speech", "sheriff_speech", "sheriff_pk",
          "withdraw", "hunter", "badge", "interview", "plan"}


def parse_voice(spec):
    """'zh-CN-YunxiNeural;pitch=-12Hz;rate=-5%' → (音色, 参数)"""
    parts = [x.strip() for x in (spec or "").split(";") if x.strip()]
    voice = parts[0] if parts else JUDGE_VOICE
    kw = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            if k in ("pitch", "rate", "volume"):
                kw[k] = v
    return voice, kw


def jobs_from_log(log):
    jobs = []
    for e in log["events"]:
        if e["type"] not in VOICED or not (e.get("speech") or "").strip():
            continue
        if e["type"] == "plan" and "pov_seat" not in log:  # 开局OS只在第一视角里出现
            continue
        spec = JUDGE_VOICE if e["type"] == "judge" else (e.get("voice") or JUDGE_VOICE)
        jobs.append((e["i"], e["speech"].strip(), spec))
    return jobs


def duration(path):
    """解码成 PCM 数采样点，比读文件头更准"""
    import subprocess
    import imageio_ffmpeg
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", path,
                          "-f", "s16le", "-ac", "1", "-ar", "24000", "-"], capture_output=True).stdout
    return len(raw) / 2 / 24000


async def synth(job, out_dir, sem, done, total):
    import edge_tts
    i, text, spec = job
    path = os.path.join(out_dir, f"{i:04d}.mp3")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        done[0] += 1
        return i, path
    voice, kw = parse_voice(spec)
    async with sem:
        for attempt in range(4):
            try:
                await edge_tts.Communicate(text, voice, **kw).save(path)
                break
            except Exception as ex:  # 网络抖动时重试
                if attempt == 3:
                    print(f"  ⚠ 第{i}条配音失败：{ex}")
                    return i, None
                await asyncio.sleep(2 * (attempt + 1))
    done[0] += 1
    print(f"  配音 {done[0]}/{total}")
    return i, path


async def run(log_path, workers):
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)
    out_dir = os.path.join(os.path.dirname(os.path.abspath(log_path)), "audio")
    os.makedirs(out_dir, exist_ok=True)
    jobs = jobs_from_log(log)
    sem = asyncio.Semaphore(workers)
    done = [0]
    results = await asyncio.gather(*(synth(j, out_dir, sem, done, len(jobs)) for j in jobs))
    timing_path = os.path.join(out_dir, "timing.json")
    timing = {}
    if os.path.exists(timing_path):
        with open(timing_path, encoding="utf-8") as f:
            timing = json.load(f)
    for i, path in results:
        if path and str(i) not in timing:
            timing[str(i)] = {"file": os.path.basename(path), "sec": round(duration(path), 3)}
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False, indent=1)
    failed = sum(1 for _, p in results if not p)
    total_sec = sum(v["sec"] for v in timing.values())
    print(f"完成：{len(timing)} 句，总时长约 {total_sec/60:.1f} 分钟" + (f"，{failed} 句失败（重跑会补上）" if failed else ""))


def main():
    ap = argparse.ArgumentParser(description="给对局记录配音")
    ap.add_argument("log", help="log.json 或 log_povN.json 的路径")
    ap.add_argument("--workers", type=int, default=4, help="同时生成几句（太大可能被限流）")
    args = ap.parse_args()
    try:
        import edge_tts  # noqa: F401
        import imageio_ffmpeg  # noqa: F401
    except ImportError:
        sys.exit("先安装依赖：pip install edge-tts imageio-ffmpeg")
    asyncio.run(run(args.log, args.workers))


if __name__ == "__main__":
    main()
