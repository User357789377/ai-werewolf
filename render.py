# -*- coding: utf-8 -*-
"""
网杀界面动画渲染：把对局记录做成竖屏手机画面的视频。

画面：左右两列各 6 个头像，谁发言谁的头像亮起来；中间是聊天区（发言气泡、法官公告、
狼人频道、票型卡片）；底部是当前发言人和声波；出局采访单独弹出采访卡。

用法：
  python render.py out/某局/log_pov5.json                 # 渲染 5 号视角（先跑 tts.py 配音）
  python render.py out/某局/log.json                      # 上帝视角（所有身份都显示）
  python render.py out/某局/log_pov5.json --preview 60    # 只渲染前 60 秒，看效果
  python render.py out/某局/log_pov5.json --snap 5,30,90  # 只导出这几个时间点的截图
依赖：pip install pillow numpy imageio-ffmpeg
头像：assets/avatars/<玩家名>.png；想换成自己的图，直接同名替换即可。
没有配音（没跑 tts.py）时会按字数估算时长，生成无声视频，适合先看节奏。
"""
import argparse
import json
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920

ROLE_SHORT = {"狼人": "狼", "村民": "民", "预言家": "预", "女巫": "女", "猎人": "猎", "白痴": "白"}
ROLE_COLOR = {"狼人": (214, 64, 64), "村民": (110, 130, 150), "预言家": (126, 84, 222),
              "女巫": (48, 160, 110), "猎人": (206, 122, 38), "白痴": (226, 168, 30)}
VOICED = {"judge", "speech", "last_words", "pk_speech", "sheriff_speech", "sheriff_pk",
          "withdraw", "hunter", "badge", "interview", "plan"}
TAG = {"speech": "发言", "last_words": "遗言", "pk_speech": "PK发言", "sheriff_speech": "警上发言",
       "sheriff_pk": "警上PK", "withdraw": "退水", "hunter": "猎人开枪", "badge": "警徽",
       "wolf_chat": "狼人频道"}

THEME = {
    "day": dict(bg=((255, 243, 226), (255, 214, 186)), panel=(255, 255, 255, 215), text=(44, 40, 52),
                sub=(120, 110, 125), bubble=(255, 255, 255), pill=(60, 50, 70, 38), card=(255, 255, 255, 240),
                accent=(255, 128, 64)),
    "night": dict(bg=((14, 20, 50), (44, 30, 86)), panel=(32, 38, 78, 215), text=(236, 236, 248),
                  sub=(170, 176, 210), bubble=(58, 66, 118), pill=(255, 255, 255, 34), card=(40, 46, 92, 245),
                  accent=(140, 170, 255)),
}
WOLF_BUBBLE = (120, 32, 44)

# 左列 1-6 号，右列 7-12 号
COL_X = (108, W - 108)
ROW_Y = [310 + k * 232 for k in range(6)]
AV = 150                      # 座位头像直径
CHAT = (212, 170, 868, 1636)  # 聊天区 left, top, right, bottom
BOTTOM = (40, 1664, W - 40, 1888)

# ---------------- 字体 ----------------
FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
]
_font_path = None
_fonts = {}


def font(size):
    global _font_path
    if _font_path is None:
        _font_path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), "")
        if not _font_path:
            sys.exit("找不到中文字体，请用 --font 指定一个 .ttf/.ttc 字体文件")
    if size not in _fonts:
        idx = 2 if "NotoSansCJK" in _font_path else 0  # Noto 的 ttc 里第 3 个是简体中文
        _fonts[size] = ImageFont.truetype(_font_path, size, index=idx)
    return _fonts[size]


def wrap(text, f, width):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if f.getlength(cur + ch) > width and cur:
            if ch in "，。！？、；：）》」』”’…,.!?;:)—" and len(cur) > 1:  # 标点不放行首：把前一个字一起带到下一行
                lines.append(cur[:-1])
                cur = cur[-1] + ch
                continue
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur or not lines:
        lines.append(cur)
    return lines


def gradient(size, top, bottom):
    w, h = size
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for c in range(3):
        arr[:, :, c] = np.linspace(top[c], bottom[c], h, dtype=np.float32)[:, None]
    return Image.fromarray(arr, "RGB")


# ---------------- 头像 ----------------
class Avatars:
    def __init__(self, players):
        self.src = {}
        palette = [(217, 119, 87), (245, 197, 66), (77, 107, 254), (59, 130, 246), (90, 90, 102), (255, 159, 28),
                   (109, 74, 255), (200, 103, 74), (244, 231, 161), (255, 233, 210), (79, 70, 229), (66, 133, 244)]
        for p in players:
            path = os.path.join(HERE, "assets", "avatars", f"{p['name']}.png")
            if os.path.exists(path):
                im = Image.open(path).convert("RGBA")
            else:  # 没有图就用色块加名字首字
                im = Image.new("RGBA", (512, 512), palette[(p["seat"] - 1) % 12] + (255,))
                d = ImageDraw.Draw(im)
                d.text((256, 256), p["name"][:1], font=font(260), fill=(255, 255, 255), anchor="mm")
            self.src[p["seat"]] = im
        self.cache = {}

    def get(self, seat, size, gray=False):
        key = (seat, size, gray)
        if key not in self.cache:
            im = self.src[seat].resize((size, size), Image.LANCZOS)
            mask = Image.new("L", (size * 4, size * 4), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
            mask = mask.resize((size, size), Image.LANCZOS)
            if gray:
                g = im.convert("L").convert("RGBA")
                im = Image.blend(g, Image.new("RGBA", g.size, (40, 40, 48, 255)), 0.35)
            im.putalpha(mask)
            self.cache[key] = im
        return self.cache[key]


# ---------------- 聊天消息 ----------------
class Msg:
    def __init__(self, kind, text, seat=None, tag="", private=False, lines=None):
        self.kind, self.text, self.seat, self.tag = kind, text, seat, tag
        self.private, self.lines = private, lines or []
        self.visible = len(text)
        self._key, self._img = None, None

    def image(self, r, theme):
        key = (self.visible, theme, self.tag)
        if key != self._key:
            self._key, self._img = key, self._draw(r, theme)
        return self._img

    def _draw(self, r, theme):
        T = THEME[theme]
        width = CHAT[2] - CHAT[0] - 24
        text = self.text[:self.visible]
        if self.kind in ("sys", "private"):
            f = font(28)
            ls = wrap(text, f, width - 80)
            h = 20 + 40 * len(ls)
            im = Image.new("RGBA", (width, h + 14), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            tw = max(f.getlength(l) for l in ls) + 44
            x0 = (width - tw) / 2
            fill = (126, 84, 222, 70) if self.kind == "private" else T["pill"]
            d.rounded_rectangle((x0, 0, x0 + tw, h), radius=22, fill=fill)
            col = (190, 160, 255) if (self.kind == "private" and theme == "night") else (
                (110, 70, 200) if self.kind == "private" else T["sub"])
            for k, l in enumerate(ls):
                d.text((width / 2, 10 + 40 * k + 20), l, font=f, fill=col, anchor="mm")
            return im
        if self.kind == "vote":
            f, fb = font(28), font(32)
            rows = self.lines
            h = 76 + 46 * len(rows)
            im = Image.new("RGBA", (width, h + 16), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((20, 0, width - 20, h), radius=26, fill=T["card"], outline=T["accent"], width=3)
            d.text((width / 2, 38), text, font=fb, fill=T["accent"], anchor="mm")
            for k, (left, right) in enumerate(rows):
                y = 88 + 46 * k
                d.text((60, y), left, font=fb, fill=T["text"], anchor="lm")
                d.text((width - 60, y), right, font=f, fill=T["sub"], anchor="rm")
            return im
        # 发言气泡 / 狼人频道
        f, fn = font(32), font(24)
        av = 70
        bw = width - av - 40
        ls = wrap(text or " ", f, bw - 40)
        bh = 28 + 46 * len(ls)
        h = 38 + bh
        im = Image.new("RGBA", (width, h + 18), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        im.alpha_composite(r.av.get(self.seat, av), (6, 4))
        name = r.players[self.seat - 1]["name"]
        head = f"{self.seat}号 {name}"
        d.text((av + 22, 16), head, font=fn, fill=T["sub"], anchor="lm")
        if self.tag:
            x = av + 34 + fn.getlength(head)
            tw = fn.getlength(self.tag) + 20
            tag_col = WOLF_BUBBLE if self.kind == "wolf" else T["accent"]
            d.rounded_rectangle((x, 2, x + tw, 31), radius=12, fill=tag_col)
            d.text((x + tw / 2, 16), self.tag, font=fn, fill=(255, 255, 255), anchor="mm")
        fill = WOLF_BUBBLE if self.kind == "wolf" else T["bubble"]
        col = (255, 236, 236) if self.kind == "wolf" else T["text"]
        tw = max(f.getlength(l) for l in ls) + 40
        d.rounded_rectangle((av + 20, 38, av + 20 + max(tw, 90), 38 + bh), radius=22, fill=fill)
        for k, l in enumerate(ls):
            d.text((av + 40, 38 + 14 + 46 * k + 23), l, font=f, fill=col, anchor="lm")
        return im


# ---------------- 渲染器 ----------------
class Renderer:
    def __init__(self, log, timing, fps):
        self.log, self.timing, self.fps = log, timing, fps
        self.players = log["players"]
        self.pov = log.get("pov_seat")
        self.av = Avatars(self.players)
        self.alive = {p["seat"]: True for p in self.players}
        self.sheriff = None
        self.known = set()
        if self.pov:
            self.known.add(self.pov)
            if self.players[self.pov - 1]["role"] == "狼人":
                self.known |= {p["seat"] for p in self.players if p["role"] == "狼人"}
        else:
            self.known = {p["seat"] for p in self.players}
        self.msgs = []
        self.theme, self.day = "night", 0
        self.speaker, self.speaker_tag = None, ""
        self.vote_badges = {}
        self.overlay = None       # ("interview", seat, Msg) / ("intro",) / ("outro",)
        self.dirty = True
        self.static = None
        self.bg = {k: gradient((W, H), *THEME[k]["bg"]) for k in THEME}
        self.fade = None          # (from_theme, start_t)

    # ---- 时间轴 ----
    def build(self):
        segs = [dict(kind="intro", dur=3.5)]
        ev = self.log["events"]
        k = 0
        while k < len(ev):
            e = ev[k]
            t = e["type"]
            if t in ("vote", "sheriff_vote"):
                group = []
                while k < len(ev) and ev[k]["type"] == t:
                    group.append(ev[k])
                    k += 1
                segs.append(dict(kind="vote", dur=2.2, ev=group[0], group=group))
                continue
            k += 1
            if t in ("death", "sheriff", "reveal"):
                segs.append(dict(kind="state", dur=0, ev=e))
            elif t == "setup":
                if self.pov and e["seat"] == self.pov:
                    segs.append(dict(kind="private", dur=2.5, ev=e))
            elif t in ("seer", "witch"):
                segs.append(dict(kind="private", dur=2.2, ev=e))
            elif t == "wolf_chat":
                dur = 1.0 if e["speech"] == "✓" else max(2.0, len(e["speech"]) / 9 + 0.8)
                segs.append(dict(kind="wolf", dur=dur, ev=e))
            elif t == "chapter":  # 精华版的章节卡
                segs.append(dict(kind="chapter", dur=e.get("dur", 2.8), ev=e))
            elif t == "plan" and not (self.pov and e["seat"] == self.pov):
                continue  # 开局OS只在这个人自己的第一视角里出现
            elif t in VOICED and (e.get("speech") or "").strip():
                a = self.timing.get(str(e["i"]))
                dur = (a["sec"] if a else len(e["speech"]) / 4.3 + 0.4) + 0.45
                kind = t if t in ("interview", "plan") else ("judge" if t == "judge" else "voice")
                if kind == "voice" and e.get("delay"):  # 思考超时：开口前先沉默一会儿（压缩显示，最多 6 秒）
                    segs.append(dict(kind="hesitate", dur=min(6.0, 1.5 + e["delay"] / 30), ev=e))
                segs.append(dict(kind=kind, dur=dur, ev=e, audio=a))
            elif t == "judge":
                segs.append(dict(kind="judge", dur=1.4, ev=e))
        segs.append(dict(kind="outro", dur=7.0))
        t = 0.0
        for s in segs:
            s["start"] = t
            t += s["dur"]
        self.total = t
        return segs

    # ---- 状态 ----
    def apply(self, s, t):
        kind, e = s["kind"], s.get("ev")
        if e:
            theme = "night" if e["phase"] == "夜" else "day"
            if e.get("section"):  # 结尾揭晓：公开所有身份，回到白天
                theme = "day"
                self.known = {p["seat"] for p in self.players}
            if theme != self.theme:
                self.fade = (self.theme, t)
                self.theme = theme
            self.day = e["day"]
        if getattr(self, "active", None) is not None:  # 上一句打字机效果补全
            self.active.visible = len(self.active.text)
            self.active = None
        if kind not in ("judge", "state"):
            self.vote_badges = {}
        self.speaker, self.speaker_tag, self.overlay = None, "", None
        self.dirty = True
        if kind == "intro":
            self.overlay = ("intro",)
        elif kind == "chapter":
            self.overlay = ("chapter", e["speech"], e.get("subtitle", ""))
        elif kind == "outro":
            self.known = {p["seat"] for p in self.players}
            self.overlay = ("outro",)
        elif kind == "state":
            if e["type"] == "death":
                self.alive[e["seat"]] = False
            elif e["type"] == "sheriff":
                self.sheriff = e["target"]
            elif e["type"] == "reveal":
                self.known.add(e["seat"])
        elif kind == "judge":
            self.msgs.append(Msg("sys", e["speech"]))
            if s.get("audio") or len(e["speech"]) > 0:
                self.speaker, self.speaker_tag = 0, "法官"
        elif kind == "private":
            text = e["speech"]
            if e["type"] == "setup":
                text = "你的" + text
            who = "仅你可见" if self.pov else "私密"
            self.msgs.append(Msg("private", f"{who} · {text}"))
        elif kind == "wolf":
            m = Msg("wolf", e["speech"], e["seat"], TAG["wolf_chat"])
            m.visible = 0
            self.msgs.append(m)
            s["msg"] = self.active = m
            self.speaker, self.speaker_tag = e["seat"], "狼人频道 · 打字中"
        elif kind == "hesitate":
            self.speaker, self.speaker_tag = e["seat"], f"迟迟没开口……（多想了 {e['delay']} 秒）"
        elif kind == "voice":
            tag = TAG.get(e["type"], "")
            m = Msg("speech", e["speech"], e["seat"], tag)
            m.visible = 0
            self.msgs.append(m)
            s["msg"] = self.active = m
            self.speaker, self.speaker_tag = e["seat"], tag or "发言"
        elif kind in ("interview", "plan"):
            m = Msg("speech", e["speech"], e["seat"])
            m.visible = 0
            s["msg"] = m
            self.overlay = (kind, e["seat"], m)
            self.known.add(e["seat"])
        elif kind == "vote":
            self.vote_card(s)
        self.msgs = self.msgs[-40:]

    def vote_card(self, s):
        group = s["group"]
        title = "警长投票" if group[0]["type"] == "sheriff_vote" else "投票结果"
        by_target, abstain = {}, []
        for v in group:
            if v["target"]:
                w = 1.5 if "1.5" in (v["speech"] or "") else 1
                by_target.setdefault(v["target"], []).append((v["seat"], w))
            else:
                abstain.append(v["seat"])
        rows = []
        self.vote_badges = {}
        for tgt, vs in sorted(by_target.items(), key=lambda x: -sum(w for _, w in x[1])):
            n = sum(w for _, w in vs)
            self.vote_badges[tgt] = n
            rows.append((f"{tgt}号  {n:g}票", "← " + "、".join(str(a) for a, _ in vs)))
        if abstain:
            rows.append(("弃票", "、".join(str(a) for a in abstain)))
        self.msgs.append(Msg("vote", title, lines=rows))

    # ---- 画面 ----
    def draw_static(self):
        T = THEME[self.theme]
        im = self.bg[self.theme].copy().convert("RGBA")
        d = ImageDraw.Draw(im)
        # 顶栏
        title = f"第{self.day}{'夜' if self.theme == 'night' else '天'}" if self.day else "AI 狼人杀"
        d.text((W / 2, 72), title, font=font(46), fill=T["text"], anchor="mm")
        icon_x = W / 2 - font(46).getlength(title) / 2 - 46
        if self.theme == "night":
            d.ellipse((icon_x - 20, 52, icon_x + 20, 92), fill=(250, 226, 140))
            d.ellipse((icon_x - 8, 46, icon_x + 28, 84), fill=self.bg["night"].getpixel((int(icon_x), 60)))
        else:
            d.ellipse((icon_x - 18, 54, icon_x + 18, 90), fill=(255, 176, 64))
        if self.pov:
            me = self.players[self.pov - 1]
            sub = f"本期视角：{self.pov}号 {me['name']}（{me['role']}）"
        else:
            sub = "上帝视角"
        d.text((W / 2, 124), sub, font=font(26), fill=T["sub"], anchor="mm")
        # 聊天区
        panel = Image.new("RGBA", (CHAT[2] - CHAT[0], CHAT[3] - CHAT[1]), (0, 0, 0, 0))
        ImageDraw.Draw(panel).rounded_rectangle((0, 0, panel.width - 1, panel.height - 1), radius=30, fill=T["panel"])
        y = panel.height - 12
        for m in reversed(self.msgs):
            mi = m.image(self, self.theme)
            if y - mi.height < 10:
                break
            y -= mi.height
            panel.alpha_composite(mi, (12, y))
        im.alpha_composite(panel, (CHAT[0], CHAT[1]))
        # 座位
        for p in self.players:
            self.draw_seat(im, d, p, T)
        # 底栏
        self.draw_bottom(im, d, T)
        self.static = im.convert("RGB")
        self.dirty = False

    def seat_xy(self, seat):
        col = 0 if seat <= 6 else 1
        return COL_X[col], ROW_Y[(seat - 1) % 6]

    def draw_seat(self, im, d, p, T):
        seat = p["seat"]
        x, y = self.seat_xy(seat)
        alive = self.alive[seat]
        r = AV // 2
        d.ellipse((x - r - 6, y - r - 6, x + r + 6, y + r + 6), fill=(255, 255, 255) if alive else (120, 120, 130))
        im.alpha_composite(self.av.get(seat, AV, gray=not alive), (x - r, y - r))
        # 座位号
        d.ellipse((x - r - 8, y - r - 8, x - r + 38, y - r + 38), fill=(40, 36, 52))
        d.text((x - r + 15, y - r + 15), str(seat), font=font(26), fill=(255, 255, 255), anchor="mm")
        # 名字
        name = p["name"]
        f = font(24)
        while f.getlength(name) > 190 and len(name) > 2:
            name = name[:-1]
        d.text((x, y + r + 26), name, font=f, fill=T["text"] if alive else T["sub"], anchor="mm")
        # 警长
        if self.sheriff == seat:
            cx, cy = x + r - 8, y - r + 8
            d.ellipse((cx - 24, cy - 24, cx + 24, cy + 24), fill=(245, 190, 60), outline=(150, 100, 20), width=3)
            d.text((cx, cy), "警", font=font(26), fill=(110, 60, 0), anchor="mm")
        # 身份
        if seat in self.known:
            role = p["role"]
            cx, cy = x + r - 6, y + r - 10
            d.rounded_rectangle((cx - 26, cy - 20, cx + 26, cy + 20), radius=12, fill=ROLE_COLOR[role])
            d.text((cx, cy), ROLE_SHORT[role], font=font(26), fill=(255, 255, 255), anchor="mm")
        if self.pov == seat:
            cx, cy = x - r + 8, y + r - 10
            d.rounded_rectangle((cx - 24, cy - 20, cx + 24, cy + 20), radius=12, fill=(40, 170, 90))
            d.text((cx, cy), "我", font=font(26), fill=(255, 255, 255), anchor="mm")
        if not alive:
            stamp = Image.new("RGBA", (150, 60), (0, 0, 0, 0))
            sd = ImageDraw.Draw(stamp)
            sd.rounded_rectangle((2, 2, 148, 58), radius=10, outline=(220, 50, 50), width=5)
            sd.text((75, 30), "出局", font=font(34), fill=(220, 50, 50), anchor="mm")
            stamp = stamp.rotate(18, expand=True, resample=Image.BICUBIC)
            im.alpha_composite(stamp, (x - stamp.width // 2, y - stamp.height // 2))
        if seat in self.vote_badges:
            n = self.vote_badges[seat]
            cx = x + (r + 44 if seat <= 6 else -r - 44)
            d.ellipse((cx - 30, y - 30, cx + 30, y + 30), fill=(230, 60, 60), outline=(255, 255, 255), width=4)
            d.text((cx, y), f"{n:g}", font=font(30), fill=(255, 255, 255), anchor="mm")

    def draw_bottom(self, im, d, T):
        box = Image.new("RGBA", (BOTTOM[2] - BOTTOM[0], BOTTOM[3] - BOTTOM[1]), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle((0, 0, box.width - 1, box.height - 1), radius=32, fill=T["panel"])
        im.alpha_composite(box, (BOTTOM[0], BOTTOM[1]))
        cy = (BOTTOM[1] + BOTTOM[3]) // 2
        x0 = BOTTOM[0] + 40
        if self.speaker is None:
            msg = "天黑请闭眼……" if self.theme == "night" else "等待发言……"
            d.text((W / 2, cy), msg, font=font(36), fill=T["sub"], anchor="mm")
            return
        if self.speaker == 0:
            d.ellipse((x0, cy - 70, x0 + 140, cy + 70), fill=(60, 52, 80))
            d.text((x0 + 70, cy), "法官", font=font(40), fill=(255, 255, 255), anchor="mm")
            name, tag = "法官", "公告"
        else:
            im.alpha_composite(self.av.get(self.speaker, 140), (x0, cy - 70))
            name = f"{self.speaker}号 {self.players[self.speaker - 1]['name']}"
            tag = self.speaker_tag
        d.text((x0 + 170, cy - 26), name, font=font(40), fill=T["text"], anchor="lm")
        d.text((x0 + 170, cy + 30), tag, font=font(28), fill=T["accent"], anchor="lm")

    def draw_dynamic(self, frame, t, seg):
        d = ImageDraw.Draw(frame)
        T = THEME[self.theme]
        if self.speaker and seg["kind"] in ("voice", "wolf", "hesitate"):
            x, y = self.seat_xy(self.speaker)
            r = AV // 2 + 12 + 5 * math.sin(t * 7)
            d.ellipse((x - r, y - r, x + r, y + r), outline=T["accent"], width=8)
        if self.speaker is not None and seg["kind"] in ("voice", "judge"):
            bx, cy = BOTTOM[2] - 330, (BOTTOM[1] + BOTTOM[3]) // 2
            for k in range(18):
                a = abs(math.sin(t * 9 + k * 0.9)) * abs(math.sin(t * 3.1 + k * 0.37))
                h = 10 + 70 * a
                d.rounded_rectangle((bx + k * 16, cy - h / 2, bx + k * 16 + 8, cy + h / 2), radius=4, fill=T["accent"])
        if seg["kind"] == "wolf":
            bx, cy = BOTTOM[2] - 200, (BOTTOM[1] + BOTTOM[3]) // 2
            for k in range(3):
                on = int(t * 3) % 3 == k
                d.ellipse((bx + k * 40, cy - 10, bx + k * 40 + 20, cy + 10), fill=T["accent"] if on else T["sub"])

    def draw_overlay(self, frame, t, seg):
        o = self.overlay
        T = THEME["day"]
        alpha = {"intro": 235, "outro": 242, "interview": 205, "plan": 205, "chapter": 225}[o[0]]
        lay = Image.new("RGBA", (W, H), (10, 8, 20, alpha))
        d = ImageDraw.Draw(lay)
        if o[0] == "chapter":
            _, title, sub = o
            p = max(0.0, min(1.0, (t - seg["start"]) / 0.35))  # 标题从下往上滑入
            y = 860 + (1 - p) * 60
            d.text((W / 2, y), title, font=font(96), fill=(255, 255, 255), anchor="mm")
            half = max(4, 70 * p)
            d.rounded_rectangle((W / 2 - half, y + 78, W / 2 + half, y + 86), radius=4, fill=(255, 196, 120))
            if sub:
                d.text((W / 2, y + 150), sub, font=font(48), fill=(255, 214, 170), anchor="mm")
        elif o[0] == "intro":
            d.text((W / 2, 700), "AI 狼人杀", font=font(120), fill=(255, 255, 255), anchor="mm")
            d.text((W / 2, 840), "12 位 AI 同台 · 预女猎白", font=font(46), fill=(255, 210, 160), anchor="mm")
            if self.pov:
                me = self.players[self.pov - 1]
                d.text((W / 2, 960), f"本期视角：{self.pov}号 {me['name']}", font=font(44), fill=(255, 255, 255), anchor="mm")
            for i, p in enumerate(self.players):
                x = 120 + (i % 6) * 168
                y = 1150 + (i // 6) * 190
                lay.alpha_composite(self.av.get(p["seat"], 130), (x - 65 + 10, y - 65))
        elif o[0] == "outro":
            win = next((e["speech"] for e in reversed(self.log["events"]) if "胜利" in (e.get("speech") or "")), "")
            d.text((W / 2, 360), win.replace("游戏结束，", "") or "游戏结束", font=font(72), fill=(255, 220, 120), anchor="mm")
            d.text((W / 2, 470), "全员身份揭晓", font=font(40), fill=(255, 255, 255), anchor="mm")
            for i, p in enumerate(self.players):
                x = 200 + (i % 3) * 340
                y = 640 + (i // 3) * 300
                lay.alpha_composite(self.av.get(p["seat"], 170, gray=not self.alive[p["seat"]]), (x - 85, y - 85))
                role = p["role"]
                d.rounded_rectangle((x - 60, y + 92, x + 60, y + 134), radius=14, fill=ROLE_COLOR[role])
                d.text((x, y + 113), role, font=font(28), fill=(255, 255, 255), anchor="mm")
                d.text((x, y + 162), f"{p['seat']}号 {p['name']}", font=font(26), fill=(230, 230, 240), anchor="mm")
        elif o[0] in ("interview", "plan"):
            kind, seat, m = o
            title, note, color = (("出局采访", "场上的玩家听不到这段采访", (230, 70, 90)) if kind == "interview"
                                  else ("开局 OS", "只有观众能听到", (90, 110, 220)))
            p = self.players[seat - 1]
            d.rounded_rectangle((70, 330, W - 70, 1560), radius=40, fill=T["card"])
            d.rounded_rectangle((W / 2 - 150, 300, W / 2 + 150, 366), radius=33, fill=color)
            d.text((W / 2, 333), title, font=font(38), fill=(255, 255, 255), anchor="mm")
            lay.alpha_composite(self.av.get(seat, 280), (W // 2 - 140, 420))
            d.text((W / 2, 750), f"{seat}号 {p['name']}", font=font(46), fill=T["text"], anchor="mm")
            role = p["role"]
            d.rounded_rectangle((W / 2 - 80, 800, W / 2 + 80, 852), radius=16, fill=ROLE_COLOR[role])
            d.text((W / 2, 826), role, font=font(32), fill=(255, 255, 255), anchor="mm")
            f = font(38)
            for k, l in enumerate(wrap(m.text[:m.visible], f, W - 260)):
                d.text((130, 910 + k * 58), l, font=f, fill=T["text"], anchor="lm")
            d.text((W / 2, 1520), note, font=font(26), fill=T["sub"], anchor="mm")
        frame.alpha_composite(lay)

    def draw_flair(self, frame, text, dt):
        """花字印章：盖在聊天区上方，弹一下再停住"""
        if not hasattr(self, "_flair") or self._flair[0] != text:
            f = font(64)
            tw = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(text, font=f))
            im = Image.new("RGBA", (tw + 90, 130), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((6, 6, tw + 84, 124), radius=26, fill=(255, 214, 64, 245), outline=(40, 20, 10, 255), width=6)
            d.text(((tw + 90) / 2, 65), text, font=f, fill=(40, 20, 10), anchor="mm")
            self._flair = (text, im.rotate(6, expand=True, resample=Image.BICUBIC))
        im = self._flair[1]
        dt = max(0.0, dt)
        p = min(1.0, dt / 0.18)
        scale = 1.35 - 0.35 * p  # 从大到小“盖章”
        if abs(scale - 1) > 0.01:
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.BICUBIC)
        a = int(255 * min(1.0, dt / 0.12))
        if a < 255:
            im = im.copy()
            im.putalpha(im.getchannel("A").point(lambda v: v * a // 255))
        # 贴在底部“正在说话”那一栏的右上角
        frame.alpha_composite(im, (W - 24 - im.width, 1668 - im.height // 2))

    def compose(self, t, seg):
        m = seg.get("msg")
        if m is not None:
            p = min(1.0, (t - seg["start"]) / max(0.3, seg["dur"] * 0.88))
            v = int(len(m.text) * p)
            if v != m.visible:
                m.visible = v
                if seg["kind"] not in ("interview", "plan"):
                    self.dirty = True
        if self.dirty:
            self.draw_static()
        frame = self.static
        if self.fade and t - self.fade[1] < 0.6:
            frame = Image.blend(self.bg[self.fade[0]], frame, (t - self.fade[1]) / 0.6)
        frame = frame.convert("RGBA")
        self.draw_dynamic(frame, t, seg)
        e = seg.get("ev")
        if e and e.get("flair") and seg["kind"] not in ("chapter", "hesitate"):
            self.draw_flair(frame, e["flair"], t - seg["start"])
        if self.overlay:
            self.draw_overlay(frame, t, seg)
        return frame.convert("RGB")


def infer_state(events):
    """旧版记录没有状态事件：根据法官公告和猎人开枪补出 death / sheriff / reveal"""
    import re
    out = []

    def state(typ, e, seat=None, target=None):
        return {"i": None, "day": e["day"], "phase": e["phase"], "type": typ, "seat": seat, "name": "",
                "role": None, "voice": None, "speech": "", "target": target, "public": True, "audience": "all"}

    for k, e in enumerate(events):
        out.append(e)
        if e["type"] == "hunter" and e["seat"]:
            out.insert(len(out) - 1, state("reveal", e, e["seat"]))
            continue
        if e["type"] != "judge":
            continue
        t = e["speech"] or ""
        m = re.search(r"昨晚死亡的是：(.+?)。", t)
        if m:
            for n in re.findall(r"(\d+)号", m.group(1)):
                out.append(state("death", e, int(n)))
        m = re.search(r"^(\d+)号被放逐", t)
        if m:
            nxt = next((x for x in events[k + 1:] if x["type"] == "judge"), None)
            if nxt and "翻牌" in (nxt["speech"] or ""):
                out.append(state("reveal", e, int(m.group(1))))
            else:
                out.append(state("death", e, int(m.group(1))))
        m = re.search(r"^(\d+)号被猎人带走", t)
        if m:
            out.append(state("death", e, int(m.group(1))))
        m = re.search(r"(\d+)号当选警长|只剩(\d+)号，自动当选|警徽移交给(\d+)号", t)
        if m:
            out.append(state("sheriff", e, target=int(next(g for g in m.groups() if g))))
        if "警徽被撕" in t or "警徽流失" in t:
            out.append(state("sheriff", e, target=None))
    return out


def mix_audio(segs, audio_dir, total, path, sr=24000):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    buf = np.zeros(int(total * sr) + sr, dtype=np.int32)
    for s in segs:
        a = s.get("audio")
        if not a:
            continue
        f = os.path.join(audio_dir, a["file"])
        raw = subprocess.run([ff, "-v", "error", "-i", f, "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
                             capture_output=True).stdout
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.int32)
        st = int((s["start"] + 0.1) * sr)
        buf[st:st + len(pcm)] += pcm[:max(0, len(buf) - st)]
    buf = np.clip(buf, -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(buf.tobytes())


def main():
    global _font_path
    ap = argparse.ArgumentParser(description="网杀界面动画渲染")
    ap.add_argument("log", help="log.json 或 log_povN.json")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--preview", type=float, default=0, help="只渲染前多少秒")
    ap.add_argument("--snap", default="", help="只导出这些时间点的截图，如 5,30,90")
    ap.add_argument("--font", default=None, help="中文字体文件路径")
    ap.add_argument("--out", default=None, help="输出视频路径")
    args = ap.parse_args()
    if args.font:
        _font_path = args.font

    with open(args.log, encoding="utf-8") as f:
        log = json.load(f)
    if not any(e["type"] in ("death", "interview") for e in log["events"]):  # 采访文件本来就没有状态事件
        print("这份记录是旧版程序打的，从法官公告里推断谁出局、谁拿警徽。")
        log["events"] = infer_state(log["events"])
    base = os.path.dirname(os.path.abspath(args.log))
    audio_dir = os.path.join(base, "audio")
    timing = {}
    tp = os.path.join(audio_dir, "timing.json")
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as f:
            timing = json.load(f)
    else:
        print("没找到配音（audio/timing.json），按字数估算时长，生成无声视频。先跑 tts.py 就有声音。")

    r = Renderer(log, timing, args.fps)
    segs = r.build()
    total = min(r.total, args.preview) if args.preview else r.total
    snaps = sorted(float(x) for x in args.snap.split(",") if x.strip())
    print(f"成片时长约 {r.total/60:.1f} 分钟" + (f"，本次渲染前 {total:.0f} 秒" if args.preview else ""))

    name = os.path.splitext(os.path.basename(args.log))[0]
    out = args.out or os.path.join(base, f"{name}.mp4")
    proc = None
    if not snaps:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(args.fps), "-i", "-"]
        if timing:
            wav = os.path.join(base, f"{name}_audio.wav")
            mix_audio(segs, audio_dir, total, wav)
            cmd += ["-i", wav, "-c:a", "aac", "-b:a", "160k"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-t", f"{total:.2f}", out]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    n_total = int(total * args.fps)
    frame_i = 0
    si = 0
    for s in segs:
        if s["start"] > total:
            break
        r.apply(s, s["start"])
        n = int(round((s["start"] + s["dur"]) * args.fps)) - frame_i
        for _ in range(max(0, n)):
            if frame_i >= n_total:
                break
            t = frame_i / args.fps
            if snaps:
                if si < len(snaps) and t >= snaps[si]:
                    img = r.compose(t, s)
                    p = os.path.join(base, f"{name}_snap_{snaps[si]:g}s.png")
                    img.save(p)
                    print("截图", p)
                    si += 1
            else:
                proc.stdin.write(r.compose(t, s).tobytes())
                if frame_i % (args.fps * 30) == 0:
                    print(f"  渲染进度 {t/60:.1f}/{total/60:.1f} 分钟")
            frame_i += 1
    if proc:
        proc.stdin.close()
        proc.wait()
        print("视频已生成：", out)


if __name__ == "__main__":
    main()
