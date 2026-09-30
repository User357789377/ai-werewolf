#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
精华版剪辑：从一局完整的 log.json 里挑片段，按某个玩家的视角，加章节卡和花字，输出一份新的记录。
新记录照样可以用 tts.py 配音、render.py 出画面，最后再进剪映微调。

用法：
  python highlight.py out/某局/log.json cut_fable.json
  → 生成 out/某局/highlight_pov8/log.json 和 script.md（先看 script.md 确认剪得对不对）
  → python tts.py out/某局/highlight_pov8/log.json
  → python render.py out/某局/highlight_pov8/log.json

剪辑清单（cut_*.json）怎么写：
  "pov"      视角玩家的座位号（null 表示上帝视角）
  "keep"     要保留、或要加花字的片段。每条用 day / phase / type / seat / contains 定位一条记录：
               excerpt   只保留这几段原话（必须逐字出自原发言），中间用“……”连起来；不写就保留整段
               flair     画面上盖一个花字印章，比如“悍跳！”
               keep_cut  截取片段后，原来跟在后面的“X号发言时间到，掐麦”是否保留（默认不保留）
             发言类（发言、警上发言、遗言、PK、警徽）只有写进 keep 的才会保留；
             投票、法官公告、狼人夜聊、死亡这些默认都保留，用 keep 可以给它们加花字。
  "drop"     默认会保留、但想删掉的记录（写法同上）
  "chapters" 章节卡：{"before": 定位, "title": "...", "subtitle": "..."}，插在那条记录前面
  "reveal"   结尾的场下采访金句：{"seat": 12, "excerpt": [...]}，放在游戏结束之后
"""
import json
import os
import sys

SPEECHY = {"speech", "sheriff_speech", "pk_speech", "sheriff_pk", "last_words", "badge", "interview", "plan"}
STATE = {"death", "sheriff", "reveal"}
LABEL = {"judge": "法官", "setup": "身份", "wolf_chat": "狼人夜聊", "seer": "预言家查验", "witch": "女巫",
         "speech": "发言", "last_words": "遗言", "hunter": "猎人开枪", "vote": "投票", "pk_speech": "PK发言",
         "interview": "场下采访", "sheriff_speech": "警上发言", "withdraw": "退水", "sheriff_vote": "警长投票",
         "sheriff_pk": "警上PK", "badge": "警徽", "plan": "开局OS", "chapter": "章节"}


def squash(s):
    return "".join((s or "").split())


def matches(e, m):
    for k in ("day", "phase", "type", "seat"):
        if k in m and e.get(k) != m[k]:
            return False
    if "contains" in m and squash(m["contains"]) not in squash(e.get("speech")):
        return False
    return True


def find(events, m, what):
    hits = [k for k, e in enumerate(events) if matches(e, m)]
    nth = m.get("nth", 1)
    if len(hits) < nth:
        raise SystemExit(f"❌ {what} 没找到对应的记录：{json.dumps(m, ensure_ascii=False)}")
    if len(hits) > 1 and "nth" not in m:
        print(f"  ⚠ {what} 匹配到 {len(hits)} 条，用了第一条（可以加 nth 指定）：{json.dumps(m, ensure_ascii=False)}")
    return hits[nth - 1]


def excerpt(text, parts, what):
    """只保留这几段原话；每段必须逐字出现在原文里（忽略空格换行）"""
    flat = squash(text)
    out = []
    for p in parts:
        if squash(p) not in flat:
            raise SystemExit(f"❌ {what} 的 excerpt 不是原话（要逐字复制）：{p}")
        out.append(p.strip().strip("…"))
    lead = "……" if text.startswith("……") else ""
    return lead + "……".join(out)


def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法：python highlight.py out/某局/log.json cut_xxx.json")
    log_path, cut_path = sys.argv[1], sys.argv[2]
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)
    with open(cut_path, encoding="utf-8") as f:
        cut = json.load(f)
    players, allev = log["players"], log["events"]
    if allev and "audience" not in allev[0]:
        raise SystemExit("这份 log.json 是旧版程序生成的，没有记录“谁知道”，没法按视角剪")
    pov = cut.get("pov")

    def visible(e):
        return pov is None or e["audience"] == "all" or pov in e["audience"]

    events = [dict(e) for e in allev if visible(e) and e["type"] != "interview"]

    # 1. 标记保留：发言类默认不留，其余默认留
    keep = [e["type"] not in SPEECHY and not (e["type"] == "setup" and e["seat"] != pov) for e in events]
    for m in cut.get("keep", []):
        k = find(events, m, "keep")
        keep[k] = True
        e = events[k]
        if m.get("excerpt"):
            e["speech"] = excerpt(e["speech"], m["excerpt"], f"{e['seat']}号第{e['day']}{e['phase']}的{LABEL.get(e['type'], e['type'])}")
            e["_excerpted"] = not m.get("keep_cut")
        if m.get("flair"):
            e["flair"] = m["flair"]
    for m in cut.get("drop", []):
        keep[find(events, m, "drop")] = False

    # 2. “掐麦”跟着它前面那段发言走：发言删了、或者只截了前面几句，掐麦也删
    for k, e in enumerate(events):
        if e["type"] == "judge" and "掐麦" in e["speech"] and k > 0:
            prev = events[k - 1]
            if not keep[k - 1] or prev.get("_excerpted"):
                keep[k] = False

    # 3. 章节卡
    chapters = {}
    for c in cut.get("chapters", []):
        k = find(events, c["before"], f"章节「{c['title']}」")
        chapters.setdefault(k, []).append(c)

    out = []
    for k, e in enumerate(events):
        for c in chapters.get(k, []):
            out.append({"day": e["day"], "phase": e["phase"], "type": "chapter", "seat": None, "name": "章节",
                        "role": None, "voice": None, "speech": c["title"], "subtitle": c.get("subtitle", ""),
                        "target": None, "public": True, "audience": "all"})
        if keep[k]:
            e.pop("_excerpted", None)
            out.append(e)

    # 4. 结尾：场下采访金句
    rev = cut.get("reveal", [])
    if rev:
        last = out[-1]
        out.append({"day": last["day"], "phase": "天", "type": "chapter", "seat": None, "name": "章节", "role": None,
                    "voice": None, "speech": cut.get("reveal_title", "场下采访"),
                    "subtitle": cut.get("reveal_subtitle", "出局的玩家怎么说"), "target": None, "public": True,
                    "audience": "all", "section": "揭晓"})
        interviews = [e for e in allev if e["type"] == "interview"]
        for r in rev:
            k = find(interviews, {"seat": r["seat"], **({"contains": r["contains"]} if "contains" in r else {})},
                     f"{r['seat']}号的采访")
            e = dict(interviews[k])
            if r.get("excerpt"):
                e["speech"] = excerpt(e["speech"], r["excerpt"], f"{e['seat']}号的采访")
            e["section"] = "揭晓"
            e["audience"] = "all"
            e["day"], e["phase"] = last["day"], "天"  # 画面顶部统一显示最后一天
            out.append(e)

    for n, e in enumerate(out):
        e["i"] = n + 1

    name = f"highlight_pov{pov}" if pov else "highlight"
    out_dir = os.path.join(os.path.dirname(os.path.abspath(log_path)), cut.get("folder", name))
    os.makedirs(out_dir, exist_ok=True)
    res = {"winner": log.get("winner"), "players": players, "events": out}
    if pov:
        res["pov_seat"], res["pov_role"] = pov, players[pov - 1]["role"]
    with open(os.path.join(out_dir, "log.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    # 预览剧本
    lines = [f"# 精华版剪辑预览（{'%d号 %s 的视角' % (pov, players[pov - 1]['name']) if pov else '上帝视角'}）", ""]
    for e in out:
        if e["type"] in STATE:
            continue
        if e["type"] == "chapter":
            lines += ["", f"## 【{e['speech']}】{e.get('subtitle', '')}", ""]
            continue
        who = f"{e['seat']}号 {e['name']}" if e["seat"] else "法官"
        flair = f"  〔花字：{e['flair']}〕" if e.get("flair") else ""
        lines.append(f"**[{LABEL.get(e['type'], e['type'])}] {who}**：{e['speech']}{flair}")
        lines.append("")
    with open(os.path.join(out_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # 估算时长（按字数；配音以后会更准）
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import render
        r = render.Renderer(res, {}, 30)
        r.build()
        est = f"，预计成片约 {r.total / 60:.1f} 分钟"
    except Exception as ex:  # 没装 numpy / pillow 时跳过估算
        est = f"（估算时长失败：{ex}）"
    kept_speech = sum(1 for e in out if e["type"] in SPEECHY)
    print(f"已生成：{out_dir}{os.sep}log.json 和 script.md —— 保留 {len(out)} 条记录（其中发言 {kept_speech} 段）{est}")
    print(f"下一步：python tts.py {os.path.join(out_dir, 'log.json')}")


if __name__ == "__main__":
    main()
