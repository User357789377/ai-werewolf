# -*- coding: utf-8 -*-
"""生成 12 个 AI 的原创吉祥物头像（不使用各家官方 logo）。输出 assets/avatars/<名字>.png"""
import os
import cairosvg

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "avatars")
INK = "#2B2B2B"
W = 6  # 描边粗细


def face(cx, cy, s=1.0, ink=INK, blush=True):
    """通用的沙雕脸：两只大眼睛 + 小嘴 + 腮红"""
    ex, ey, er = 22 * s, 0, 11 * s
    parts = []
    for dx in (-ex, ex):
        parts.append(f'<circle cx="{cx+dx}" cy="{cy+ey}" r="{er}" fill="#fff" stroke="{ink}" stroke-width="{4*s}"/>')
        parts.append(f'<circle cx="{cx+dx+2*s}" cy="{cy+ey+2*s}" r="{er*0.5}" fill="{ink}"/>')
        parts.append(f'<circle cx="{cx+dx+4*s}" cy="{cy+ey-1*s}" r="{er*0.18}" fill="#fff"/>')
    if blush:
        for dx in (-ex - 12 * s, ex + 12 * s):
            parts.append(f'<ellipse cx="{cx+dx}" cy="{cy+18*s}" rx="{8*s}" ry="{5*s}" fill="#FF8FA3" opacity="0.7"/>')
    parts.append(f'<path d="M{cx-10*s} {cy+20*s} Q{cx} {cy+30*s} {cx+10*s} {cy+20*s}" fill="none" '
                 f'stroke="{ink}" stroke-width="{4*s}" stroke-linecap="round"/>')
    return "".join(parts)


def glasses_round(cx, cy, s=1.0):
    return (f'<circle cx="{cx-22*s}" cy="{cy}" r="{17*s}" fill="none" stroke="{INK}" stroke-width="{5*s}"/>'
            f'<circle cx="{cx+22*s}" cy="{cy}" r="{17*s}" fill="none" stroke="{INK}" stroke-width="{5*s}"/>'
            f'<line x1="{cx-5*s}" y1="{cy}" x2="{cx+5*s}" y2="{cy}" stroke="{INK}" stroke-width="{5*s}"/>')


def sunglasses(cx, cy, s=1.0):
    return (f'<path d="M{cx-46*s} {cy-10*s} H{cx+46*s} L{cx+40*s} {cy+12*s} Q{cx+24*s} {cy+18*s} {cx+8*s} {cy+8*s} '
            f'L{cx} {cy-2*s} L{cx-8*s} {cy+8*s} Q{cx-24*s} {cy+18*s} {cx-40*s} {cy+12*s} Z" fill="{INK}"/>'
            f'<path d="M{cx-34*s} {cy-4*s} L{cx-22*s} {cy-4*s}" stroke="#fff" stroke-width="{3*s}" opacity="0.7"/>')


def svg(bg, body, deco_back="", deco_front=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="512" height="512">
<defs><clipPath id="c"><circle cx="128" cy="128" r="124"/></clipPath></defs>
<g clip-path="url(#c)"><rect width="256" height="256" fill="{bg}"/>{deco_back}{body}{deco_front}</g>
</svg>'''


def blob(color, cx=128, cy=150, r=78):
    return f'<rect x="{cx-r}" y="{cy-r}" width="{2*r}" height="{2*r}" rx="{r*0.8}" fill="{color}" stroke="{INK}" stroke-width="{W}"/>'


def mascots():
    m = {}

    # 1 Claude Opus：陶土色团子 + 礼帽 + 单片眼镜
    m["Claude Opus"] = svg("#F4E4D7", blob("#D97757") + face(128, 150),
        deco_front=(f'<rect x="92" y="34" width="72" height="50" rx="6" fill="{INK}"/>'
                    f'<rect x="92" y="68" width="72" height="10" fill="#B8412E"/>'
                    f'<ellipse cx="128" cy="84" rx="58" ry="10" fill="{INK}"/>'
                    f'<circle cx="150" cy="150" r="17" fill="none" stroke="#C9A227" stroke-width="5"/>'
                    f'<path d="M166 156 Q176 190 168 214" fill="none" stroke="#C9A227" stroke-width="3"/>'))

    # 2 GPT-6 Astra：金色星星 + 墨镜
    star = ("M128 52 L150 108 L210 110 L163 146 L180 204 L128 170 L76 204 L93 146 L46 110 L106 108 Z")
    m["GPT-6 Astra"] = svg("#1F2937",
        f'<path d="{star}" fill="#F5C542" stroke="{INK}" stroke-width="{W}" stroke-linejoin="round"/>' + face(128, 140, 0.85),
        deco_front=sunglasses(128, 138, 0.8))

    # 3 DeepSeek：蓝色小鲸鱼 + 圆框眼镜
    whale = (f'<path d="M190 150 Q222 118 232 132 Q222 150 236 172 Q214 170 190 162 Z" fill="#4D6BFE" stroke="{INK}" stroke-width="{W}" stroke-linejoin="round"/>'
             f'<ellipse cx="118" cy="158" rx="84" ry="64" fill="#4D6BFE" stroke="{INK}" stroke-width="{W}"/>'
             f'<ellipse cx="112" cy="190" rx="54" ry="22" fill="#DDE6FF" opacity="0.9"/>')
    spout = (f'<path d="M118 92 Q112 70 100 62 M118 92 Q124 70 138 62 M118 92 V64" stroke="#7FB2FF" stroke-width="6" fill="none" stroke-linecap="round"/>')
    m["DeepSeek"] = svg("#DDE6FF", whale + face(112, 150), deco_back=spout, deco_front=glasses_round(112, 150))

    # 4 混元：蓝色汤圆 + 侦探猎鹿帽 + 烟斗
    m["元宝"] = m["混元"] = svg("#DCEBFF",
        f'<circle cx="128" cy="156" r="80" fill="#3B82F6" stroke="{INK}" stroke-width="{W}"/>' + face(128, 158),
        deco_front=(f'<path d="M60 104 Q128 40 196 104 Z" fill="#A0784A" stroke="{INK}" stroke-width="{W}" stroke-linejoin="round"/>'
                    f'<path d="M84 84 L172 84 M72 96 L184 96 M100 64 L100 104 M128 56 L128 104 M156 64 L156 104" stroke="#7A5530" stroke-width="3"/>'
                    f'<path d="M58 104 L40 116 L66 112 Z M198 104 L216 116 L190 112 Z" fill="#A0784A" stroke="{INK}" stroke-width="4"/>'
                    f'<path d="M142 180 L176 188" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
                    f'<path d="M172 176 h20 v16 q0 10 -10 10 q-10 0 -10 -10 Z" fill="#6B4226" stroke="{INK}" stroke-width="4"/>'
                    f'<path d="M184 170 q6 -10 0 -18 q-6 -8 2 -16" stroke="#BBB" stroke-width="3" fill="none"/>'))

    # 5 Grok：暗色小恶魔团子 + 小角 + 坏笑
    grok_face = (f'<circle cx="106" cy="148" r="11" fill="#fff" stroke="#111" stroke-width="4"/><circle cx="108" cy="150" r="5" fill="#111"/>'
                 f'<circle cx="150" cy="148" r="11" fill="#fff" stroke="#111" stroke-width="4"/><circle cx="152" cy="150" r="5" fill="#111"/>'
                 f'<path d="M92 132 L118 140 M164 132 L138 140" stroke="#111" stroke-width="5" stroke-linecap="round"/>'
                 f'<path d="M110 176 Q134 190 152 170" fill="none" stroke="#111" stroke-width="5" stroke-linecap="round"/>'
                 f'<path d="M140 180 l4 8 l4 -7" fill="#fff" stroke="#111" stroke-width="2"/>')
    m["Grok"] = svg("#2B2B2B",
        f'<path d="M84 96 L70 52 L108 82 Z M172 96 L186 52 L148 82 Z" fill="#E23B3B" stroke="#111" stroke-width="{W}" stroke-linejoin="round"/>'
        + blob("#5A5A66") + grok_face,
        deco_front=f'<path d="M196 196 q20 10 22 30 q-8 -6 -16 -4" fill="none" stroke="#E23B3B" stroke-width="6" stroke-linecap="round"/>')

    # 6 GPT-6 Sol：太阳 + 反戴棒球帽
    rays = "".join(
        f'<path d="M128 150 L{128+112*c:.1f} {150+112*s:.1f}" stroke="#FFB347" stroke-width="18" stroke-linecap="round"/>'
        for c, s in [(1, 0), (0.707, 0.707), (0, 1), (-0.707, 0.707), (-1, 0), (-0.707, -0.707), (0, -1), (0.707, -0.707)])
    m["GPT-6 Sol"] = svg("#FFF1D6", rays +
        f'<circle cx="128" cy="150" r="72" fill="#FF9F1C" stroke="{INK}" stroke-width="{W}"/>' + face(128, 152),
        deco_front=(f'<path d="M66 118 Q128 60 190 118 Z" fill="#2F80ED" stroke="{INK}" stroke-width="{W}" stroke-linejoin="round"/>'
                    f'<path d="M66 118 Q46 116 40 128 Q56 132 74 124 Z" fill="#2F80ED" stroke="{INK}" stroke-width="4"/>'
                    f'<circle cx="128" cy="84" r="6" fill="{INK}"/>'))

    # 7 千问：紫色水滴 + 问号呆毛 + 耳机
    drop = f'<path d="M128 66 Q200 150 188 184 Q176 226 128 226 Q80 226 68 184 Q56 150 128 66 Z" fill="#6D4AFF" stroke="{INK}" stroke-width="{W}" stroke-linejoin="round"/>'
    m["千问"] = svg("#EDE7FF", drop + face(128, 168),
        deco_back=(f'<path d="M112 46 Q112 22 132 22 Q152 22 150 42 Q148 56 132 62 L130 72" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'),
        deco_front=(f'<path d="M66 176 Q64 104 128 104 Q192 104 190 176" fill="none" stroke="{INK}" stroke-width="8"/>'
                    f'<rect x="54" y="160" width="24" height="40" rx="10" fill="#FF6B9A" stroke="{INK}" stroke-width="5"/>'
                    f'<rect x="178" y="160" width="24" height="40" rx="10" fill="#FF6B9A" stroke="{INK}" stroke-width="5"/>'))

    # 8 Claude Fable：陶土色团子 + 巫师尖帽 + 羽毛笔
    m["Claude Fable"] = svg("#F6E1D6", blob("#C8674A") + face(128, 152),
        deco_front=(f'<path d="M78 92 L138 16 Q140 40 176 92 Z" fill="#4C3F91" stroke="{INK}" stroke-width="{W}" stroke-linejoin="round"/>'
                    f'<ellipse cx="128" cy="92" rx="66" ry="12" fill="#4C3F91" stroke="{INK}" stroke-width="{W}"/>'
                    f'<path d="M122 52 l4 10 l10 1 l-8 6 l3 10 l-9 -6 l-9 6 l3 -10 l-8 -6 l10 -1 Z" fill="#FFD166"/>'
                    f'<path d="M198 214 L214 118 Q236 136 210 172" fill="#FFFFFF" stroke="{INK}" stroke-width="4"/>'))

    # 9 Kimi：月亮 + 睡帽
    m["Kimi"] = svg("#1A1A2E",
        f'<circle cx="128" cy="154" r="80" fill="#F4E7A1" stroke="{INK}" stroke-width="{W}"/>'
        f'<circle cx="84" cy="130" r="10" fill="#E3D27E"/><circle cx="170" cy="190" r="14" fill="#E3D27E"/><circle cx="160" cy="120" r="7" fill="#E3D27E"/>'
        + face(124, 158),
        deco_back=('<circle cx="40" cy="60" r="3" fill="#fff"/><circle cx="214" cy="48" r="2.5" fill="#fff"/><circle cx="222" cy="120" r="2" fill="#fff"/>'),
        deco_front=(f'<path d="M62 104 Q120 50 190 96 Q214 60 236 70 Q212 88 196 110 Z" fill="#5B8DEF" stroke="{INK}" stroke-width="{W}" stroke-linejoin="round"/>'
                    f'<path d="M58 106 Q128 86 198 108" stroke="#fff" stroke-width="10" fill="none" stroke-linecap="round"/>'
                    f'<circle cx="236" cy="72" r="12" fill="#fff" stroke="{INK}" stroke-width="4"/>'))

    # 10 豆包：包子 + 褶子 + 领结
    bun = (f'<path d="M44 196 Q44 96 128 80 Q212 96 212 196 Q128 214 44 196 Z" fill="#FFF7EC" stroke="{INK}" stroke-width="{W}" stroke-linejoin="round"/>'
           f'<path d="M128 80 Q116 96 104 92 M128 80 Q140 96 152 92 M128 80 Q126 98 128 104" stroke="#E0C9A6" stroke-width="5" fill="none" stroke-linecap="round"/>')
    m["豆包"] = svg("#FFE9D2", bun + face(128, 150),
        deco_front=(f'<path d="M128 214 L100 200 L100 228 Z M128 214 L156 200 L156 228 Z" fill="#E94F4F" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>'
                    f'<circle cx="128" cy="214" r="7" fill="#C73A3A" stroke="{INK}" stroke-width="3"/>'))

    # 11 GLM：猫头鹰 + 学士帽
    owl = (f'<path d="M72 104 L66 70 L98 92 Z M184 104 L190 70 L158 92 Z" fill="#4F46E5" stroke="{INK}" stroke-width="{W}" stroke-linejoin="round"/>'
           f'<ellipse cx="128" cy="160" rx="76" ry="74" fill="#4F46E5" stroke="{INK}" stroke-width="{W}"/>'
           f'<ellipse cx="128" cy="196" rx="44" ry="34" fill="#C7D2FE"/>'
           f'<circle cx="106" cy="148" r="22" fill="#E0E7FF"/><circle cx="150" cy="148" r="22" fill="#E0E7FF"/>'
           f'<path d="M122 170 L134 170 L128 182 Z" fill="#F59E0B" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>')
    owl_face = (f'<circle cx="106" cy="148" r="12" fill="#fff" stroke="{INK}" stroke-width="4"/><circle cx="108" cy="150" r="6" fill="{INK}"/>'
                f'<circle cx="150" cy="148" r="12" fill="#fff" stroke="{INK}" stroke-width="4"/><circle cx="152" cy="150" r="6" fill="{INK}"/>')
    m["GLM"] = svg("#E0E7FF", owl + owl_face,
        deco_front=(f'<path d="M62 70 L128 44 L194 70 L128 96 Z" fill="{INK}"/>'
                    f'<rect x="100" y="76" width="56" height="20" fill="{INK}"/>'
                    f'<path d="M190 70 L196 108" stroke="#F5C542" stroke-width="4"/><circle cx="196" cy="112" r="6" fill="#F5C542"/>'))

    # 12 Gemini：双色团子 + 贝雷帽
    m["Gemini"] = svg("#E8F0FE",
        '<defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="0"><stop offset="0.5" stop-color="#4285F4"/><stop offset="0.5" stop-color="#A142F4"/></linearGradient></defs>'
        + blob("url(#g)") + face(128, 152),
        deco_front=(f'<ellipse cx="116" cy="84" rx="62" ry="22" fill="#E53935" stroke="{INK}" stroke-width="{W}" transform="rotate(-10 116 84)"/>'
                    f'<path d="M116 62 l2 -12" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>'))
    return m


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, code in mascots().items():
        cairosvg.svg2png(bytestring=code.encode("utf-8"), write_to=os.path.join(OUT, f"{name}.png"))
        print("生成", name)


if __name__ == "__main__":
    main()
