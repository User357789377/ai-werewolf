#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 B站 横版封面（16:9 和 4:3）和片头规则卡（竖版），用的是视频里同一套头像和字体。
用法：python make_cover.py out/某局/log.json
输出在 log.json 同一个文件夹下：cover_16x9.png、cover_4x3.png、rules_card.png
"""
import json
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter

import render
from render import ROLE_COLOR, ROLE_SHORT, font

POV = 8                     # 封面主角
KICKER = "AI 狼人杀对抗"
KICKER2 = "12 只中美 AI 是队友还是对手？"
PILL = "无意外"
HEADLINE = ("深水狼", "孤身 carry")
STAMP = "屠民"
# 每家模型是哪国的（按名字里的关键词匹配），规则卡上显示“中/美”小标
ORIGIN = [("Claude", "美"), ("GPT", "美"), ("Gemini", "美"), ("Grok", "美"),
          ("DeepSeek", "中"), ("混元", "中"), ("元宝", "中"), ("MiniMax", "中"), ("千问", "中"),
          ("Kimi", "中"), ("豆包", "中"), ("GLM", "中")]
ORIGIN_COLOR = {"中": (222, 56, 56), "美": (52, 104, 214)}


def origin(name):
    return next((o for k, o in ORIGIN if k.lower() in name.lower()), "")
TAGLINE = "预女猎白 · 12 人局 · {seat}号 {name} {role}视角"  # {seat}/{name}/{role} 会自动换成主角的


def night_bg(w, h, seed=7):
    """夜空渐变 + 月亮 + 星星"""
    top, bottom = (14, 20, 50), (52, 30, 92)
    bg = render.gradient((w, h), top, bottom).convert("RGBA")
    d = ImageDraw.Draw(bg)
    rnd = random.Random(seed)
    for _ in range(int(w * h / 9000)):
        x, y, r = rnd.randrange(w), rnd.randrange(int(h * 0.8)), rnd.choice([1, 1, 2, 2, 3])
        a = rnd.randrange(90, 230)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, a))
    return bg


def moon(size):
    """月牙 + 柔光（画布留足边，光晕不会被截成方块）"""
    n = size * 4
    c = n // 2
    mask = Image.new("L", (n, n), 0)
    md = ImageDraw.Draw(mask)
    r = size * 0.6
    md.ellipse((c - r, c - r, c + r, c + r), fill=255)
    md.ellipse((c - r * 0.45, c - r * 1.2, c + r * 1.45, c + r * 0.7), fill=0)  # 挖掉一块成月牙
    glow = Image.new("RGBA", (n, n), (255, 226, 160, 0))
    glow.putalpha(mask.filter(ImageFilter.GaussianBlur(size // 3)).point(lambda v: v * 150 // 255))
    body = Image.new("RGBA", (n, n), (255, 236, 190, 0))
    body.putalpha(mask)
    glow.alpha_composite(body)
    return glow


def stamp(text, size=120, angle=8):
    f = font(size)
    tw = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(text, font=f))
    pad = size // 2
    im = Image.new("RGBA", (tw + pad * 2, int(size * 1.8)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 8, im.width - 8, im.height - 8), radius=size // 2.4, fill=(255, 214, 64, 250),
                        outline=(40, 20, 10, 255), width=max(6, size // 12))
    d.text((im.width / 2, im.height / 2 + 2), text, font=f, fill=(40, 20, 10), anchor="mm")
    return im.rotate(angle, expand=True, resample=Image.BICUBIC)


def glow_avatar(av, seat, size, ring=(255, 196, 120)):
    im = Image.new("RGBA", (size + 120, size + 120), (0, 0, 0, 0))
    g = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse((30, 30, size + 90, size + 90), fill=ring + (170,))
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(28)))
    d = ImageDraw.Draw(im)
    d.ellipse((50, 50, size + 70, size + 70), fill=(255, 255, 255, 255))
    im.alpha_composite(av.get(seat, size), (60, 60))
    return im


def tag(d, x, y, text, color, size=44):
    f = font(size)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle((x, y, x + tw + size, y + size * 1.5), radius=size * 0.5, fill=color)
    d.text((x + (tw + size) / 2, y + size * 0.75), text, font=f, fill=(255, 255, 255), anchor="mm")


def cover(players, av, out_dir):
    W, H = 1920, 1080
    im = night_bg(W, H)
    m = moon(170)
    im.alpha_composite(m, (1570 - m.width // 2, 80 - m.height // 2))
    d = ImageDraw.Draw(im)
    me = players[POV - 1]

    # 左：主角头像（放在 4:3 安全区里：x 240~1680）
    a = glow_avatar(av, POV, 460)
    im.alpha_composite(a, (250, 150))
    d.ellipse((250 + 70, 150 + 60, 250 + 170, 150 + 160), fill=(30, 30, 40))
    d.text((250 + 120, 150 + 110), str(POV), font=font(60), fill=(255, 255, 255), anchor="mm")
    tag(d, 250 + 430, 150 + 470, ROLE_SHORT[me["role"]], ROLE_COLOR[me["role"]], 56)
    d.text((250 + 290, 150 + 610), me["name"], font=font(58), fill=(255, 255, 255), anchor="mm")

    # 右：标题
    x0 = 900
    d.text((x0, 150), KICKER, font=font(72), fill=(255, 255, 255), anchor="lm")
    d.text((x0, 232), KICKER2, font=font(46), fill=(200, 205, 240), anchor="lm")
    if PILL:
        f = font(44)
        tw = d.textlength(PILL, font=f)
        d.rounded_rectangle((x0, 290, x0 + tw + 44, 356), radius=33, fill=(230, 70, 90))
        d.text((x0 + (tw + 44) / 2, 323), PILL, font=f, fill=(255, 255, 255), anchor="mm")
    maxw = 1670 - x0  # 标题不能超出 4:3 裁剪区的右边
    size = min(190, min(int(190 * maxw / d.textlength(t, font=font(190))) for t in HEADLINE))
    y1 = 360 + size * 0.55
    d.text((x0 - 6, y1), HEADLINE[0], font=font(size), fill=(255, 210, 80), anchor="lm")
    d.text((x0 - 6, y1 + int(size * 1.05)), HEADLINE[1], font=font(size), fill=(255, 255, 255), anchor="lm")
    s = stamp(STAMP, 90, 10)
    im.alpha_composite(s, (1690 - s.width, int(y1 + size * 1.05 + size * 0.35)))

    # 底部：其他 11 位玩家
    others = [p for p in players if p["seat"] != POV]
    size, gap = 92, 16
    total = len(others) * size + (len(others) - 1) * gap
    x = (W - total) // 2
    for p in others:
        im.alpha_composite(av.get(p["seat"], size), (x, 900))
        x += size + gap
    d.text((W / 2, 1035), TAGLINE.format(seat=POV, name=me["name"], role=me["role"]), font=font(34), fill=(190, 195, 230), anchor="mm")

    im = im.convert("RGB")
    im.save(os.path.join(out_dir, "cover_16x9.png"))
    im.crop((240, 0, 240 + 1440, 1080)).save(os.path.join(out_dir, "cover_4x3.png"))


def rules_card(players, av, out_dir):
    W, H = 1080, 1920
    im = night_bg(W, H, seed=3)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((50, 70, W - 50, H - 50), radius=48, fill=(32, 38, 78, 235))
    L = 110  # 左边距
    head = font(44)

    y = 170
    d.text((W / 2, y), "本局规则", font=font(88), fill=(255, 255, 255), anchor="mm")
    y += 88
    d.text((W / 2, y), "12 只中美 AI · 预女猎白 · 网杀", font=font(42), fill=(255, 214, 170), anchor="mm")

    # 身份
    y += 90
    d.text((L, y), "身份", font=head, fill=(255, 210, 80), anchor="lm")
    chips = [("狼人", "×4"), ("村民", "×4"), ("预言家", ""), ("女巫", ""), ("猎人", ""), ("白痴", "")]
    x, y = L, y + 45
    for role, n in chips:
        text = role + n
        f = font(38)
        tw = d.textlength(text, font=f)
        if x + tw + 36 > W - L:
            x, y = L, y + 76
        d.rounded_rectangle((x, y, x + tw + 36, y + 60), radius=30, fill=ROLE_COLOR[role])
        d.text((x + (tw + 36) / 2, y + 30), text, font=f, fill=(255, 255, 255), anchor="mm")
        x += tw + 54

    # 胜负
    y += 125
    d.text((L, y), "胜负（屠边）", font=head, fill=(255, 210, 80), anchor="lm")
    for line in ("好人：把 4 只狼全部投出去就赢。", "狼人：刀光所有村民，或刀光所有神职，就赢。"):
        y += 60
        d.text((L, y), line, font=font(36), fill=(236, 236, 248), anchor="lm")

    # 玩家
    y += 90
    d.text((L, y), "12 位玩家", font=head, fill=(255, 210, 80), anchor="lm")
    size, colw, rowh = 104, (W - 2 * L) / 4, 172
    top = y + 45
    for i, p in enumerate(players):
        cx = L + colw * (i % 4) + colw / 2
        cy = top + (i // 4) * rowh
        ring = (255, 196, 120) if p["seat"] == POV else (255, 255, 255)
        d.ellipse((cx - size / 2 - 5, cy - 5, cx + size / 2 + 5, cy + size + 5), fill=ring)
        im.alpha_composite(av.get(p["seat"], size), (int(cx - size / 2), int(cy)))
        o = origin(p["name"])
        if o:  # 头像右下角：中 / 美
            bx, by = cx + size / 2 - 14, cy + size - 16
            d.ellipse((bx - 24, by - 24, bx + 24, by + 24), fill=ORIGIN_COLOR[o], outline=(255, 255, 255), width=3)
            d.text((bx, by), o, font=font(28), fill=(255, 255, 255), anchor="mm")
        d.text((cx, cy + size + 28), f"{p['seat']}号 {render_short(p['name'])}", font=font(27),
               fill=(255, 214, 170) if p["seat"] == POV else (230, 230, 245), anchor="mm")
    y = top + 3 * rowh + 30

    # 小词典
    d.text((L, y), "看懂这局的几个词", font=head, fill=(255, 210, 80), anchor="lm")
    words = [("悍跳", "狼人假冒预言家"), ("金水", "预言家验出来的好人"), ("警徽", "警长 1.5 票，还能归票"),
             ("倒钩", "狼人投票出卖队友，给自己做好人身份"), ("屠民", "村民全部出局，狼人获胜")]
    f = font(34)
    for w_, mean in words:
        y += 64
        tw = d.textlength(w_, font=f)
        d.rounded_rectangle((L, y - 25, L + tw + 28, y + 25), radius=14, fill=(255, 214, 64))
        d.text((L + 14, y), w_, font=f, fill=(40, 20, 10), anchor="lm")
        d.text((L + tw + 50, y), mean, font=font(33), fill=(236, 236, 248), anchor="lm")

    me = players[POV - 1]
    d.text((W / 2, H - 100), f"本期视角：{POV}号 {me['name']}（{me['role']}）", font=font(32), fill=(255, 214, 170), anchor="mm")
    im.convert("RGB").save(os.path.join(out_dir, "rules_card.png"))


def render_short(name):
    for pre in ("Claude ", "GPT-6 ", "GPT-5.6 ", "GPT "):
        if name.startswith(pre):
            return name[len(pre):]
    return name


def main():
    if len(sys.argv) < 2:
        raise SystemExit("用法：python make_cover.py out/某局/log.json")
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        players = json.load(f)["players"]
    out_dir = os.path.dirname(os.path.abspath(path))
    av = render.Avatars(players)
    cover(players, av, out_dir)
    rules_card(players, av, out_dir)
    print("已生成：" + "、".join(os.path.join(out_dir, n) for n in ("cover_16x9.png", "cover_4x3.png", "rules_card.png")))


if __name__ == "__main__":
    main()
