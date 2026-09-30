#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 狼人杀 · 自动法官
板子：12人 预女猎白（4狼 4民 预言家 女巫 猎人 白痴），屠边，网杀（轮流开麦，没有面杀）

用法：
  python werewolf.py --mock                   # 不调 API，用随机发言跑一局，检查流程
  python werewolf.py --config players.json    # 真实对局

输出（在 out/<时间>/ 下）：
  log.json   逐条事件：谁、什么身份、说了什么、投给谁——给配音和剪辑用
  script.md  上帝视角的可读剧本，方便挑高光

第一视角导出（从已经打完的 log.json 导出，不用重打）：
  python werewolf.py --export-pov out/xxx/log.json --seat 5       # 5号的视角
  python werewolf.py --export-pov out/xxx/log.json --seat 女巫    # 女巫的视角
  python werewolf.py --export-pov out/xxx/log.json --seat 村民    # 随机一个村民（平民视角）
  python werewolf.py --export-pov out/xxx/log.json                # 随机抽一个人
  视角玩家只看到他自己能知道的内容；出局后也不开上帝视角，照样只看公开内容（面杀规则）。
"""
import argparse
import json
import os
import random
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

WOLF, VILLAGER, SEER, WITCH, HUNTER, IDIOT = "狼人", "村民", "预言家", "女巫", "猎人", "白痴"
GODS = {SEER, WITCH, HUNTER, IDIOT}
BOARD = [WOLF] * 4 + [VILLAGER] * 4 + [SEER, WITCH, HUNTER, IDIOT]

RULES = """板子：12人 预女猎白。4狼人、4村民、预言家、女巫、猎人、白痴。
胜负（屠边）：狼人全部出局则好人胜；村民全部出局或神职全部出局则狼人胜。
夜晚：狼人共同刀一人；预言家查验一人是好人还是狼人；女巫有一瓶解药一瓶毒药，同一晚只能用一瓶，不能自救。
白天：法官公布昨晚死讯（不公布死因），存活玩家依次发言，然后投票放逐一人；平票则平票者PK发言后其他人再投，再平则当天无人出局。
猎人：出局时可以开枪带走一人（被女巫毒死不能开枪）。白痴：被投票放逐时翻牌免死，但之后失去投票权。
前两晚死亡的玩家有遗言，第三晚起夜里死亡没有遗言；白天被放逐的玩家都有遗言。
警长：第一天白天先进行警长竞选，这时还没公布昨晚死讯。想当警长的玩家上警，依次发言，发言后可以退水；没上警的玩家投票选警长，上过警的玩家（包括退水的）不能投票。平票PK一次，再平则警徽流失。
警长投票算1.5票；警长决定每天的发言从自己前一位还是后一位开始，自己最后发言归票。警长出局时可以把警徽移交给一名存活玩家，也可以撕掉警徽。白痴警长翻牌后警徽流失。
警徽流：预言家常在警上报出接下来几晚打算验谁（如“警徽流先3后9”），这样即使自己倒牌，警徽和查验信息也能传下去。
信息纪律：只有狼人知道昨晚刀了谁；只有女巫知道被刀的是谁、救没救；“平安夜”只说明昨晚没人死。公开发言时不要说出你的身份本来不可能知道的信息，否则等于自爆。查验一个活着的人完全正常，不是破绽。
时间规定：开局拿到身份后有 60 秒思考这一局怎么打。游戏内每次发言（警上发言、白天发言、PK、遗言）有 90 秒思考 + 90 秒发言，思考超时会占用发言时间，发言超时被法官掐麦。白天的操作环节（上警、退水、投票、猎人开枪、移交警徽、警长选发言顺序）每次只有 60 秒：大约 40 秒思考、20 秒做出操作。夜里更快：狼人和预言家同时睁眼，狼人一共 60 秒，几只狼同时打字、各自提刀，按多数定刀口（平票随机）；预言家验人 30 秒；狼人之后女巫用药 30 秒。超时按默认处理：不上警、不退水、弃票、当晚不验人、不用药、这只狼不说话也不提刀（狼全部超时就空刀）、不开枪、警徽流失、按默认顺序发言。所以开局那 60 秒要好好利用，把各种情况下怎么操作先想清楚，之后才能果断。熟练玩家投票时一般都会上票，只有完全没方向才弃票；警徽有 1.5 票和归票权，通常值得争取。
这是网杀：大家轮流开麦发言、看投票，看不到表情和动作。"""

STYLE = """说什么、说多少、要不要亮身份，都由你自己决定。别重复别人已经说过的话。只说话，不描述表情和动作。
提到别的玩家时，号码后面顺带说他的简称，比如“8号Fable”“10号豆包”，方便观众知道你在说谁；同一段话里第二次提到同一个人，只说号码就行。
说话方式像真人开麦聊天：短句，一句话讲一个意思，用大白话；少用书面长句，少用“第一条、第二条”这种罗列，也少大段引用别人原话。
为了游戏流畅，发言尽量精简：只做必要的分析，不说废话，不客套，不从头复述局势。没有特别可以分析的内容，可以直接说“过”，不是一定要说很多，关键在操作（投票、技能）。带点情绪，像个真人：被怀疑了可以急，抓到破绽可以得意，被冤枉了可以不爽，别像念稿的人机。
大家都是熟悉规则的老玩家，不用给别人讲解规则。但谁的操作不合老玩家的常理（比如警长安排的发言方向不对劲、该上票不上票、该跳身份不跳），你可以直接拿来当作踩他或保他的理由。

两条规矩：
1. 只能评价已经发过言的人。还没发言的人，你最多说“等他发言再看”，不许说他发言怎样。
2. 提到别人说过的话、投过的票，默认要和公开记录一致。你可以故意歪曲（比如狼人想带节奏），但那必须是你想清楚之后的策略，不能是记错或凭空瞎编。"""

ROLE_TIPS = {
    WOLF: "你的目标：和狼队友一起让好人阵营输掉（屠边）。怎么打由你自己决定。",
    VILLAGER: "你没有技能。你的目标：和好人阵营一起把狼人全部找出来。",
    SEER: "你每晚可以查验一人是好人还是狼人。你的目标：帮好人阵营找出狼人。",
    WITCH: "你有一瓶解药、一瓶毒药。你的目标：帮好人阵营找出狼人。",
    HUNTER: "你出局时可以开枪带走一人（被毒死不能开枪）。你的目标：帮好人阵营找出狼人。",
    IDIOT: "你被投票放逐时可以翻牌免死，但之后不能投票。你的目标：帮好人阵营找出狼人。",
}

OUTPUT_RULE = """回复格式：只输出一个 JSON 对象，不要有任何其他文字。先写 plan，再写 speech。
- plan：开口前的准备，只给你自己看，任何玩家都看不到，也不会进视频。先想清楚场上的情况，再决定说什么。
- speech：你说出口的话（不需要说话的环节留空）。
- 需要选目标时，target 填座位号数字。"""

INTERVIEWS = False  # 出局采访：已关闭

INTERVIEW_TASK = ("你已经出局了。现在是场下的出局采访，只有观众能看到，场上的玩家听不到，可以完全坦白。"
                  "主持人问：你是什么身份？这局里你最关键的操作，当时是怎么想的？"
                  "如果你做过不常规的操作（比如警下起跳、悍跳、自刀、倒钩、藏身份、骗药、故意歪曲别人的话、出人意料的毒或枪），"
                  "一定要把当时的思路讲清楚，这是观众最想听的。"
                  "像综艺节目的出局采访那样回答：口语化、坦白，可以自嘲或吐槽；想说多少说多少，但别逐条复盘，也别重复遗言。回答写在 speech 里。")

# 自动降低思考强度的默认表：已清空（要比的就是各家模型的真实能力）。需要时可在 players.json 里单独写 quick_extra_body
QUICK_DEFAULTS = []

# 全程思考强度：统一用低档，加快对局（狼人杀不需要高强度推理）。MiniMax 本身是自适应思考，不传。
# players.json 里写了 extra_body 就以配置为准（写 {} 表示不传任何强度参数）。模型不认这个参数时程序会自动去掉。
EFFORT_DEFAULTS = [
    ("hy4", {"reasoning_effort": "low"}),       # 混元 Hy4 只有 high / low
    ("hy3", {"reasoning_effort": "low"}),       # 元宝（混元 Hy3）也只有 high / low
    ("glm-5", {"reasoning_effort": "low"}),     # GLM-5.x 只有 max / high / low
    ("minimax", {}),
]
EFFORT_DEFAULT = {"reasoning_effort": "low"}

SPEECH_SECONDS = 90    # 每人每次游戏内发言限时（白天发言、警上发言、PK、遗言）——“阳时间”，按配音时长算
THINK_SECONDS = 90     # 轮到发言后的思考时间——“阴时间”，按实际调用耗时算；超出的部分从发言时间里扣
DECIDE_SECONDS = 60    # 所有操作环节（上警、退水、投票、验人、用药、刀人、开枪、移交警徽、选发言顺序）：约 40 秒思考 + 20 秒操作，超时按默认处理
PLAN_SECONDS = 60      # 开局拿到身份后的思考时间
WOLF_SECONDS = 60      # 狼人刀人：几只狼同时打字、提刀，一次定
SEER_SECONDS = 30      # 预言家验人（和狼人同时进行）
WITCH_SECONDS = 30     # 女巫用药（在狼人之后）
CHARS_PER_SECOND = 4.3  # 配音语速，约每秒 4.3 个字 → 90 秒约 390 字

SPEECH_RULE = (f"从轮到你开始计时，这一轮你一共有 {(THINK_SECONDS + SPEECH_SECONDS) // 60} 分钟：前 {THINK_SECONDS} 秒是思考时间，"
               f"之后是 {SPEECH_SECONDS} 秒发言时间（按正常语速大约 {int(SPEECH_SECONDS * CHARS_PER_SECOND) // 10 * 10} 字）。"
               f"思考超过 {THINK_SECONDS} 秒，超出的部分会从发言时间里扣掉；{(THINK_SECONDS + SPEECH_SECONDS) // 60} 分钟内都没开口就算过麦。发言超时的部分会被法官直接掐麦，没人听得到。"
               "所以前面的人发言时你就该开始准备，轮到你时尽快想好开口；要跳身份、报查验这类关键信息一定先说。"
               "长度按实际内容来，别凑时间：没什么新信息时一两句话或者直接说“过”就够，信息多、要对刚时再说长。")

STATE_EVENTS = ("death", "sheriff", "reveal")  # 只给动画用的状态事件，剧本里不显示

TYPE_LABEL = {
    "judge": "法官", "setup": "身份", "wolf_chat": "狼人夜聊", "seer": "预言家查验",
    "witch": "女巫", "speech": "发言", "last_words": "遗言", "hunter": "猎人开枪",
    "vote": "投票", "pk_speech": "PK发言", "interview": "出局采访", "plan": "开局OS",
    "sheriff_speech": "警上发言", "withdraw": "退水", "sheriff_vote": "警长投票",
    "sheriff_pk": "警上PK", "badge": "警徽",
    "death": "出局", "sheriff": "警长变更", "reveal": "亮身份",
}


def short_name(p):
    """玩家简称：players.json 里写了 short 就用它，否则自动去掉 Claude / GPT-6 这类前缀"""
    if getattr(p, "short", ""):
        return p.short
    for pre in ("Claude ", "GPT-6 ", "GPT-5.6 ", "GPT "):
        if p.name.startswith(pre):
            return p.name[len(pre):]
    return p.name


@dataclass
class Player:
    seat: int
    name: str
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    voice: str = ""
    style: str = ""
    temperature: float = 0.9   # 有的模型只接受固定值（比如 Kimi 只能 1）；设为 null 表示不传
    fixed_role: str = ""       # players.json 里写 "role": "狼人" 就固定这个身份
    short: str = ""            # 发言里称呼他的简称，不写就自动生成
    timeout: float = 600       # 单次请求最多等多少秒；推理模型想得久，别设太短
    extra_body: dict = None    # 额外传给接口的参数，比如 {"reasoning_effort": "low"}
    stream: bool = True        # 流式接收：边生成边回传，中转站不容易因为等太久报 504
    quick_extra_body: dict = None  # 简单决定（上警/投票/验人/用药等）时额外传的参数，用来降低思考强度
    role: str = ""
    alive: bool = True
    can_vote: bool = True
    idiot_revealed: bool = False
    private: list = field(default_factory=list)


def parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def mock_reply(p, options):
    t = random.choice(options) if options else None
    guess = random.choice([x for x in range(1, 13) if x != p.seat])
    return {
        "speech": f"（模拟发言）{p.seat}号发言，我觉得{guess}号有点问题，先听后面的。",
        "target": t,
        "action": random.choice(["none", "save", "poison", "run", "run", "pass", "stay", "stay", "withdraw", "up", "down"]),
    }


class Brain:
    """负责调用各家模型。所有模型都走 OpenAI 兼容接口，只是 base_url 和 key 不同。"""

    def __init__(self, mock=False):
        self.mock = mock
        self.clients = {}
        self.hard_fails = {}
        self._lock = threading.Lock()

    def _client(self, p):
        from openai import OpenAI
        key = (p.base_url, p.api_key_env)
        if key not in self.clients:
            # max_retries=0：关掉库自带的隐藏重试（超时后它会悄悄从头再生成，白花钱），重试由我们自己控制
            self.clients[key] = OpenAI(base_url=p.base_url, api_key=os.environ[p.api_key_env], max_retries=0)
        return self.clients[key]

    def _complete(self, p, messages, kw, deadline=None):
        cli = self._client(p)
        timeout = p.timeout if deadline is None else max(1.0, min(p.timeout, deadline - time.time()))
        if not p.stream:
            resp = cli.chat.completions.create(model=p.model, messages=messages, timeout=timeout, **kw)
            return resp.choices[0].message.content or ""
        parts = []
        stream = cli.chat.completions.create(model=p.model, messages=messages, timeout=timeout, stream=True, **kw)
        try:
            for chunk in stream:
                if deadline is not None and time.time() > deadline:
                    raise TimeoutError("超过限时")
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    parts.append(chunk.choices[0].delta.content)
        finally:
            if deadline is not None:
                stream.close()
        return "".join(parts)

    HARD_LIMIT = 6  # 同一个模型连续这么多次“硬错误”（key 失效、余额用完、模型名不对），说明这局没法正常打了

    def _hard_error(self, p, msg):
        """记一次硬错误；连续太多次就存盘结束这局（不会随机顶替它的操作）"""
        with self._lock:
            self.hard_fails[p.seat] = self.hard_fails.get(p.seat, 0) + 1
            n = self.hard_fails[p.seat]
        if n >= self.HARD_LIMIT:
            raise FatalAPIError(f"{p.seat}号 {p.name}（{p.model}）连续 {n} 次调用出错：{msg}"
                                "——多半是余额用完、key 失效或模型名不对")

    def _ok(self, p):
        with self._lock:
            self.hard_fails[p.seat] = 0

    @staticmethod
    def _fix_params(p, e, msg):
        """接口不接受某个参数（流式、思考强度、temperature）：去掉它，返回 True 表示可以再试"""
        if getattr(e, "status_code", None) != 400:
            return False
        low = msg.lower()
        if "stream" in low and p.stream:
            print(f"\n  … {p.seat}号 {p.name} 的接口不支持流式，改为普通方式")
            p.stream = False
            return True
        if any(k in low for k in ("reasoning", "thinking", "effort")) and strip_effort(p):
            print(f"\n  … {p.seat}号 {p.name} 不支持思考强度参数，改为用它的默认强度")
            return True
        if "temperature" in low and p.temperature is not None:
            print(f"\n  … {p.seat}号 {p.name} 不接受 temperature={p.temperature}，改为不传这个参数")
            p.temperature = None
            return True
        return False

    @staticmethod
    def _is_hard(e):
        code = getattr(e, "status_code", None)
        return code is not None and code not in (408, 409, 425, 429) and code < 500

    WAIT_LIMIT = 5 * 60  # 服务临时不可用（502、限流、网络）时，一次发言最多等 5 分钟，还不行就当掉线过麦

    def ask(self, p, system, user, options, quick=False, deadline=None, think_limit=None):
        if self.mock:
            return mock_reply(p, options)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if deadline is not None:  # 限时决定：超时或出错就返回 None，由调用方按弃票处理
            for _ in range(4):
                kw = {} if p.temperature is None else {"temperature": p.temperature}
                body = dict(p.extra_body or {})
                if quick and p.quick_extra_body:
                    body.update(p.quick_extra_body)
                if body:
                    kw["extra_body"] = body
                try:
                    data = parse_json(self._complete(p, messages, kw, deadline))
                except Exception as e:
                    msg = str(e).replace("\n", " ")[:120]
                    if self._fix_params(p, e, msg) and time.time() < deadline - 3:
                        continue  # 参数不被接受：修好后在剩下的时间里再试
                    if self._is_hard(e):
                        self._hard_error(p, msg)
                    return None
                if data is not None:
                    self._ok(p)
                return data
            return None
        bad_json = hard = waited = attempt = 0
        while True:
            attempt += 1
            try:
                kw = {} if p.temperature is None else {"temperature": p.temperature}
                body = dict(p.extra_body or {})
                if quick and p.quick_extra_body:
                    body.update(p.quick_extra_body)
                if body:
                    kw["extra_body"] = body
                t0 = time.time()
                try:
                    text = self._complete(p, messages, kw, t0 + think_limit if think_limit else None)
                except Exception as e:
                    if think_limit and (isinstance(e, TimeoutError) or "timed out" in str(e).lower()):
                        return {"_timeout": True, "_think": think_limit}  # 思考加发言的总时间用完了：过麦
                    raise
                data = parse_json(text)
                if data is not None:
                    self._ok(p)
                    data["_think"] = time.time() - t0
                    return data
                bad_json += 1
                if bad_json >= 4:  # 很少见：模型反复不按格式回答
                    print(f"\n  ⚠ {p.seat}号 {p.name} 连续 4 次没按格式回答，这一步随机处理")
                    return mock_reply(p, options)
                print(f"\n  … {p.seat}号 {p.name} 回复格式不对，提醒它重答")
                messages = messages + [{"role": "assistant", "content": text},
                                       {"role": "user", "content": "格式不对。请只输出一个 JSON 对象，不要任何其他文字。"}]
                continue
            except Exception as e:
                code = getattr(e, "status_code", None)
                msg = str(e).replace("\n", " ")[:120]
                # 限流、超时、网络、服务器 5xx 都是临时的：耐心等；模型名错、key 错这类是永久的：停下
                transient = code is None or code in (408, 409, 425, 429) or code >= 500
                if self._fix_params(p, e, msg):
                    continue
                if transient:
                    if waited >= self.WAIT_LIMIT:
                        print(f"\n  ⚠ {p.seat}号 {p.name} 连续 {self.WAIT_LIMIT // 60} 分钟调不通（{msg}），按掉线处理，过麦")
                        return {"_timeout": True, "_offline": True, "_think": 0}
                    wait = min(60, 5 * attempt)
                else:
                    self._hard_error(p, msg)  # 连续太多次会存盘结束这局
                    hard += 1
                    if hard >= 3:
                        print(f"\n  ⚠ {p.seat}号 {p.name} 调用出错（{msg}），这次按掉线处理，过麦")
                        return {"_timeout": True, "_offline": True, "_think": 0}
                    wait = 5
                print(f"\n  … {p.seat}号 {p.name} 调用失败（{msg}），{wait}秒后重试")
                time.sleep(wait)
                waited += wait


class FatalAPIError(Exception):
    """某个模型长时间调不通：停下这局，保存进度"""


class Game:
    def __init__(self, players, brain):
        self.ps = players
        self.brain = brain
        self.day = 0
        self.phase = "夜"
        self.public = []
        self.events = []
        self.antidote = True
        self.poison = True
        self.winner = None
        self.sheriff = None  # 警长座位号
        self._interviews = []  # 后台进行中的出局采访
        self.interviews = []   # 采访内容，单独保存

    # ---------- 工具 ----------
    def p(self, seat):
        return self.ps[seat - 1]

    def alive(self, role=None):
        return [q for q in self.ps if q.alive and (role is None or q.role == role)]

    @staticmethod
    def seats(players):
        return [q.seat for q in players]

    def emit(self, typ, text="", p=None, target=None, public=True, audience=()):
        self.events.append({
            "i": len(self.events) + 1, "day": self.day, "phase": self.phase, "type": typ,
            "seat": p.seat if p else None, "name": p.name if p else "法官",
            "role": p.role if p else None, "voice": p.voice if p else None,
            "speech": text, "target": target, "public": public,
            "audience": "all" if public else sorted(q.seat for q in audience),
        })
        if typ in STATE_EVENTS:  # 状态事件只给动画用，不进任何人的记录
            return
        label = TYPE_LABEL.get(typ, typ)
        who = f"{p.seat}号{p.name}" if p else "法官"
        line = f"[第{self.day}{self.phase}·{label}] {who}：{text}"
        if public:
            self.public.append(line)
        for q in audience:
            q.private.append(line)
        role = f"（{p.role}）" if p else ""
        print(f"{'  ' if p else ''}[{label}] {who}{role}：{text}")

    def system_prompt(self, p):
        parts = [f"这是一局纯路人的网杀狼人杀，你是{p.seat}号玩家「{p.name}」。"
                 "12 个人彼此互不认识，之前也没有一起打过，不存在以前的对局、场外的交情或恩怨；发言里不要提、也不要假设这些。"
                 "大家都是熟练的老玩家，熟悉规则和常见打法，不会犯新手错误。这只是背景设定：发言里不要提“老玩家/高手”这个说法"
                 "（可以说某个操作不合常理，但别说“高手不会这么打”）。"
                 "你要全力以赴，用尽一切合规的手段让你的阵营赢下这一局。", RULES,
                 f"你的身份：{p.role}。{ROLE_TIPS[p.role]}"]
        if p.role == WOLF:
            mates = [f"{q.seat}号{q.name}" for q in self.ps if q.role == WOLF and q is not p]
            parts.append("你的狼队友：" + "、".join(mates) + "。")
        parts.append("玩家列表（号码 + 简称）：" + "、".join(f"{q.seat}号{short_name(q)}" for q in self.ps))
        parts.append(STYLE)
        parts.append(OUTPUT_RULE)
        return "\n\n".join(parts)

    def user_prompt(self, p, task):
        dead = [q for q in self.ps if not q.alive]
        parts = ["存活：" + "、".join(f"{q.seat}号" for q in self.alive())
                 + "；已出局：" + ("、".join(f"{q.seat}号" for q in dead) or "无")
                 + "；警长：" + (f"{self.sheriff}号" if self.sheriff else "无")]
        if p.private:
            parts.append("只有你知道的信息：\n" + "\n".join(p.private))
        parts.append("公开记录：\n" + ("\n".join(self.public) if self.public else "（游戏刚开始）"))
        parts.append("现在：" + task)
        return "\n\n".join(parts)

    def ask(self, p, task, options=None, quiet=False, quick=False, deadline=None, think_limit=None):
        t0 = time.time()
        if not quiet and not self.brain.mock:
            print(f"  ⏳ {p.seat}号 {p.name} 思考中……", end="", flush=True)
        data = self.brain.ask(p, self.system_prompt(p), self.user_prompt(p, task), options, quick=quick,
                              deadline=deadline, think_limit=think_limit)
        if data is None:
            return None
        if not quiet and not self.brain.mock:
            print(f" {time.time() - t0:.0f}秒", flush=True)
        data["speech"] = str(data.get("speech") or "")
        if options is not None:
            try:
                t = int(data.get("target"))
            except (TypeError, ValueError):
                t = None
            if t not in options:
                t = random.choice(options)
            data["target"] = t
        return data

    def act(self, p, task, options=None, timeout_note="", seconds=None, quiet=False):
        """单人操作环节：限时（默认 DECIDE_SECONDS 秒，约 40 秒思考 + 20 秒操作），超时返回 None"""
        seconds = seconds or DECIDE_SECONDS
        split = "（大约 40 秒思考、20 秒操作）" if seconds == DECIDE_SECONDS else ""
        task += f"你有 {seconds} 秒{split}，超时{timeout_note}。"
        if self.brain.mock:
            return self.ask(p, task, options, quick=True)
        d = self.ask(p, task, options, quick=True, deadline=time.time() + seconds, quiet=quiet)
        if d is None and not quiet:
            print(f" ⌛ 超时，{timeout_note}", flush=True)
        return d

    def ask_all(self, players, task_of, what, default, seconds=None):
        """同时决定的环节（上警、退水、投票、开局思考）：一起问，限时，没按时决定的按 default 处理"""
        seconds = seconds or DECIDE_SECONDS
        if not players:
            return []
        if self.brain.mock:
            res = [self.ask(q, *task_of(q), quick=True) for q in players]
            for d in res:
                d["_at"] = random.random() * seconds
            return res
        print(f"  ⏳ {len(players)} 人同时{what}（限时 {seconds} 秒）……", flush=True)
        t0 = time.time()
        deadline = t0 + seconds
        out = {}
        ex = ThreadPoolExecutor(max_workers=len(players))
        futs = {ex.submit(self.ask, q, *task_of(q), quiet=True, quick=True, deadline=deadline): q for q in players}
        try:
            for f in as_completed(futs, timeout=seconds + 3):
                q = futs[f]
                try:
                    d = f.result()
                except FatalAPIError:
                    ex.shutdown(wait=False, cancel_futures=True)
                    raise
                if d is None:
                    continue
                d["_at"] = time.time() - t0
                out[q.seat] = d
                print(f"     ✓ {q.seat}号 {q.name}（{time.time() - t0:.0f}秒）", flush=True)
        except Exception:
            pass
        ex.shutdown(wait=False, cancel_futures=True)
        res = []
        for q in players:
            if q.seat in out:
                res.append(out[q.seat])
            else:
                print(f"     ⌛ {q.seat}号 {q.name} 没在 {seconds} 秒内想好", flush=True)
                res.append(dict(default, speech="", timeout=True))
        return res

    def check_win(self):
        if self.winner:
            return True
        wolves = len(self.alive(WOLF))
        villagers = len(self.alive(VILLAGER))
        gods = sum(1 for q in self.alive() if q.role in GODS)
        if wolves == 0:
            self.winner = "好人"
        elif villagers == 0 or gods == 0:
            self.winner = "狼人"
        if self.winner:
            self.emit("judge", f"游戏结束，{self.winner}阵营胜利！")
            return True
        return False

    # ---------- 流程 ----------
    def deal(self, split=None):
        """发牌：先满足 players.json 里固定的身份，再满足 --split 的阵营要求，其余随机"""
        fixed = {q.seat: q.fixed_role for q in self.ps if q.fixed_role}
        for seat, r in fixed.items():
            if r not in BOARD:
                raise SystemExit(f"{seat}号的身份「{r}」不在这个板子里，可选：狼人、村民、预言家、女巫、猎人、白痴")
        pool = BOARD[:]
        for r in fixed.values():
            if r not in pool:
                raise SystemExit(f"固定的身份太多了：{r} 这个板子里没那么多张")
            pool.remove(r)
        free = [q for q in self.ps if q.seat not in fixed]
        groups = []
        if split:
            groups = [[q.seat for q in self.ps if key.lower() in q.name.lower()] for key in split]
            for key, g in zip(split, groups):
                if not g:
                    raise SystemExit(f"--split 里的「{key}」没有匹配到任何玩家名字")
        for _ in range(20000):
            random.shuffle(pool)
            roles = dict(fixed)
            roles.update({q.seat: r for q, r in zip(free, pool)})
            camps = [{("wolf" if roles[s] == WOLF else "good") for s in g} for g in groups]
            # 每组内部同一阵营，组与组之间阵营不同
            if all(len(c) == 1 for c in camps) and len({next(iter(c)) for c in camps}) == len(camps):
                break
        else:
            raise SystemExit("按 --split 和固定身份的要求发不出牌，请放宽条件（比如狼只有 4 张，一组人太多就进不了狼阵营）")
        for q in self.ps:
            q.role = roles[q.seat]

    def pregame_plan(self):
        task = (f"你刚拿到身份，开局前有 {PLAN_SECONDS} 秒思考时间。先解读一下自己的处境：你是什么身份，坐几号，"
                "这个号码大概在前置位还是后置位发言，这对你意味着什么。然后交代你这一局准备怎么打。打法由你自己决定，不用跟别人一样。"
                "之后每个操作的时间都很短，所以现在就把各种情况下怎么做想清楚。"
                "plan：写你详细的打算，只有你自己能看到，之后每一轮都会提醒你。"
                "speech：用两三句大白话说说你对自己身份、位置的解读和这局的打法，像开局的内心独白，任何玩家都听不到。")
        answers = self.ask_all(self.ps, lambda q: (task,), "思考这一局怎么打", {"plan": ""}, seconds=PLAN_SECONDS)
        self.plans = {}
        for q, d in zip(self.ps, answers):
            plan = str(d.get("plan") or "").strip()
            os_text = str(d.get("speech") or "").strip()
            if plan:
                self.plans[q.seat] = plan
                q.private.append(f"[开局·你自己的打算] {plan}")
            if os_text or plan:
                # 开局 OS：不进任何玩家的记录，只在这个人自己的第一视角里出现
                self.events.append({"i": len(self.events) + 1, "day": self.day, "phase": self.phase, "type": "plan",
                                    "seat": q.seat, "name": q.name, "role": q.role, "voice": q.voice,
                                    "speech": os_text or plan, "target": None, "public": False, "audience": [q.seat]})
                print(f"  💭 {q.seat}号{q.name}（{q.role}）开局OS：{os_text or plan}")

    def run(self, max_days=10, split=None, out_dir=None):
        self.deal(split)
        for q in self.ps:
            text = f"身份：{q.role}"
            if q.role == WOLF:
                mates = [f"{w.seat}号" for w in self.ps if w.role == WOLF and w is not q]
                text += "，狼队友：" + "、".join(mates)
            self.emit("setup", text, q, public=False, audience=[q])
        self.emit("judge", "身份已发放，每人有 60 秒思考这一局怎么打。")
        self.pregame_plan()
        self.emit("judge", "思考时间结束，游戏开始。")
        while not self.winner:
            deaths = self.night()
            self.day_phase(deaths)
            if out_dir and not self.winner:
                self.save(out_dir, wait=False)  # 每打完一天存一次盘，中途断了也不丢
                print(f"  💾 第{self.day}天打完，已自动存盘", flush=True)
            if not self.winner and self.day >= max_days:
                self.emit("judge", f"已到第{max_days}天上限，游戏中止。")
                break

    def night(self):
        self.day += 1
        self.phase = "夜"
        self.emit("judge", f"第{self.day}夜，天黑请闭眼。")

        # 预言家和狼人同时睁眼：预言家在后台验人，狼人这边商量
        seer = self.alive(SEER)
        seer_job = None
        if seer:
            s = seer[0]
            opts = [x for x in self.seats(self.alive()) if x != s.seat]
            seer_task = "预言家请睁眼，今晚查验谁？target 填座位号，speech 留空。"
            if self.brain.mock:
                seer_d = self.act(s, seer_task, opts, "当晚不验人", seconds=SEER_SECONDS)
            else:
                ex = ThreadPoolExecutor(max_workers=1)
                seer_job = ex.submit(self.act, s, seer_task, opts, "当晚不验人", SEER_SECONDS, True)
                ex.shutdown(wait=False)

        kill = self.wolf_chat()

        if seer:
            if seer_job is not None:
                try:
                    seer_d = seer_job.result(timeout=SEER_SECONDS + 5)
                except FatalAPIError:
                    raise
                except Exception:
                    seer_d = None
                print(f"  {'✓' if seer_d else '⌛'} 预言家{s.seat}号 {s.name}{'验完了' if seer_d else ' 超时，当晚不验人'}", flush=True)
            d = seer_d
            if d is None:
                self.emit("seer", "超时，今晚没有查验", s, None, public=False, audience=[s])
            else:
                res = "狼人" if self.p(d["target"]).role == WOLF else "好人"
                self.emit("seer", f"查验{d['target']}号：{res}", s, d["target"], public=False, audience=[s])

        # 女巫
        saved, poisoned = False, None
        witch = self.alive(WITCH)
        if witch and (self.antidote or self.poison):
            wi = witch[0]
            can_save = self.antidote and kill is not None and kill != wi.seat
            knife = f"今晚{kill}号被刀了。" if kill is not None else "今晚没有人被刀。"
            task = (f"女巫请睁眼。{knife}"
                    f"解药：{'可用' if can_save else ('不能自救' if self.antidote else '已用完')}；"
                    f"毒药：{'可用' if self.poison else '已用完'}。一晚只能用一瓶。"
                    '请在 action 填 "save"（救人）、"poison"（毒人，target 填座位号）或 "none"（不用药）。speech 留空。')
            opts = [x for x in self.seats(self.alive()) if x != wi.seat]
            d = self.act(wi, task, opts, "不用药", seconds=WITCH_SECONDS)
            act = "none" if d is None else str(d.get("action", "none")).lower()
            if act == "save" and can_save:
                self.antidote, saved = False, True
                self.emit("witch", f"{kill}号被刀，使用解药救了{kill}号", wi, kill, False, [wi])
            elif act == "poison" and self.poison:
                self.poison, poisoned = False, d["target"]
                self.emit("witch", f"{kill}号被刀，使用毒药毒了{poisoned}号", wi, poisoned, False, [wi])
            else:
                why = "超时，" if d is None else ""
                self.emit("witch", (f"{kill}号被刀，" if kill is not None else "今晚没人被刀，") + why + "没有用药", wi, None, False, [wi])

        deaths = {}
        if not saved and kill is not None:
            deaths[kill] = "wolf"
        if poisoned:
            deaths[poisoned] = "poison"
        return deaths

    def wolf_chat(self):
        """狼人刀人：几只狼同时打字、各自提刀，一共 WOLF_SECONDS 秒，一次定。按多数定刀口，平票随机。"""
        wolves = self.alive(WOLF)
        targets = self.seats(self.alive())
        task = (f"狼人请睁眼。狼队友同时打字、各自提刀，一共 {WOLF_SECONDS} 秒，只有这一次，看不到队友这次说什么；"
                "按多数定刀口，平票随机。speech 是只有狼队友能看到的话，像打字一样，一两句就够，没什么要说的可以留空；"
                "target 填你想刀的座位号。")
        answers = self.ask_all(wolves, lambda w: (task, targets), "狼人刀人", {"target": None}, seconds=WOLF_SECONDS)
        got = sorted([(d["_at"], w, d) for w, d in zip(wolves, answers) if not d.get("timeout")], key=lambda x: x[0])
        picks = []
        for _, w, d in got:  # 谁先打完字，谁的话先出来
            picks.append(d["target"])
            self.emit("wolf_chat", d["speech"].strip() or f"刀{d['target']}号", w, d["target"], public=False, audience=wolves)
        if not picks:
            self.emit("judge", "狼人都没在时限内决定，今晚空刀。", public=False, audience=wolves)
            return None
        tally = Counter(picks).most_common()
        kill = random.choice([t for t, c in tally if c == tally[0][1]])
        self.emit("judge", f"狼人决定刀{kill}号。", public=False, audience=wolves)
        return kill

    def day_phase(self, deaths):
        self.phase = "天"
        if self.day == 1:
            self.sheriff_election()
            head = "警长竞选结束。"
        else:
            head = "天亮了。"
        if deaths:
            self.emit("judge", head + "昨晚死亡的是：" + "、".join(f"{s}号" for s in sorted(deaths)) + "。")
        else:
            self.emit("judge", head + "昨晚是平安夜。")
        for s in sorted(deaths):
            self.eliminate(self.p(s), deaths[s], last_words=(self.day <= 2))  # 前两晚死亡有遗言
            if self.check_win():
                return

        order = self.speech_order()
        for q in order:
            if not q.alive:
                continue
            info = self.round_info([x for x in order if x.alive or x is q], q)
            if q.seat == self.sheriff:
                task = info + "你是警长，最后一个发言。"
            else:
                task = info + "轮到你发言。"
            self.speak(q, task, "speech")
        self.vote()
        self.check_win()

    @staticmethod
    def round_info(order, me, what="发言"):
        """本轮顺序、他排第几、谁说过、谁还没说"""
        seats = [q.seat for q in order]
        k = seats.index(me.seat)
        done = seats[:k]
        todo = seats[k + 1:]
        fmt = lambda xs: "、".join(f"{x}号" for x in xs) or "无"
        return (f"本轮{what}顺序：{'→'.join(f'{x}号' for x in seats)}。你是第{k + 1}个。"
                f"本轮已经发过言：{fmt(done)}；还没发言：{fmt(todo)}。")

    def speech_order(self):
        alive = self.alive()
        sh = self.p(self.sheriff) if self.sheriff else None
        if not sh or not sh.alive:
            start = random.randrange(len(alive))
            order = alive[start:] + alive[:start]
            self.emit("judge", f"从{order[0].seat}号开始依次发言。")
            return order
        d = self.act(sh, '你是警长，请决定今天的发言顺序。action 填 "up"（从你后一位开始，座位号递增）'
                         '或 "down"（从你前一位开始，座位号递减）。你自己最后发言归票。speech 留空。', None, "按默认顺序（座位号递增）") or {}
        i = alive.index(sh)
        up = alive[i + 1:] + alive[:i]
        down = list(reversed(alive[:i])) + list(reversed(alive[i + 1:]))
        go_up = str(d.get("action", "up")).lower() != "down"
        rest = up if go_up else down
        if rest:
            self.emit("judge", f"警长{sh.seat}号选择从{rest[0].seat}号开始{'顺序' if go_up else '逆序'}发言，警长最后归票。")
        return rest + [sh]

    # ---------- 警长竞选 ----------
    def sheriff_election(self):
        self.emit("judge", "天亮了。先进行警长竞选，想上警的玩家请举手。")
        everyone = self.alive()  # 昨晚死讯还没公布，所有人都可以上警
        answers = self.ask_all(everyone, lambda q: (f'警长竞选：你要上警吗？action 填 "run"（上警）或 "pass"（不上警）。speech 留空。'
                                                    f'你有 {DECIDE_SECONDS} 秒（大约 40 秒思考、20 秒操作），超时算不上警。',),
                               "决定要不要上警", {"action": "pass"})
        wants = [(q, str(d.get("action", "pass")).lower() == "run") for q, d in zip(everyone, answers)]
        runners = [q for q, w in wants if w]
        if not runners:
            self.emit("judge", "无人上警，本局没有警长。")
            return
        self.emit("judge", "上警的玩家：" + "、".join(f"{q.seat}号" for q in runners) + "。")

        start = random.randrange(len(runners))
        order = runners[start:] + runners[:start]
        self.emit("judge", f"警上发言，从{order[0].seat}号开始。")
        for q in order:
            self.speak(q, self.round_info(order, q, "警上发言") + "你在警上，轮到你做竞选发言。", "sheriff_speech")

        # 退水只是一个动作，不能借机发言
        answers = self.ask_all(order, lambda q: ('警上发言结束。你要退水吗？action 填 "stay"（留在警上）或 "withdraw"（退水）。'
                                                 f"退水只是一个动作，不能说话，speech 留空。" + f"你有 {DECIDE_SECONDS} 秒（大约 40 秒思考、20 秒操作），超时算不退水。",),
                               "决定要不要退水", {"action": "stay"})
        decisions = [(q, str(d.get("action", "stay")).lower() == "withdraw", "")
                     for q, d in zip(order, answers)]
        remain = []
        for q, withdraw, sp in decisions:
            if withdraw:
                self.emit("withdraw", "退水。", q)
            else:
                remain.append(q)
        if not remain:
            self.emit("judge", "警上全员退水，警徽流失。")
            return
        if len(remain) == 1:
            self.set_sheriff(remain[0].seat)
            self.emit("judge", f"警上只剩{self.sheriff}号，自动当选警长。")
            return
        voters = [q for q in everyone if q not in runners]
        self.sheriff_vote(remain, voters, pk=False)

    def sheriff_vote(self, cands, voters, pk):
        names = "、".join(f"{q.seat}号" for q in cands)
        if not voters:
            self.emit("judge", "警下没有可以投票的玩家，警徽流失。")
            return
        opts = [q.seat for q in cands] + [0]
        task = f"{'警长PK投票' if pk else '警长投票'}：在{names}中选一位当警长。target 填座位号，0 表示弃票。speech 留空。"
        task += f"你有 {DECIDE_SECONDS} 秒（大约 40 秒思考、20 秒操作），超时算弃票。"
        answers = self.ask_all(voters, lambda v: (task, opts), "投票选警长", {"target": 0})
        results = [(v, d["target"], d.get("timeout")) for v, d in zip(voters, answers)]
        tally = Counter()
        for v, t, late in results:
            self.emit("sheriff_vote", f"投{t}号" if t else ("弃票（超时）" if late else "弃票"), v, t or None)
            if t:
                tally[t] += 1
        if not tally:
            self.emit("judge", "警下全员弃票，警徽流失。")
            return
        top = tally.most_common()
        self.emit("judge", "警长票型：" + "，".join(f"{s}号{c}票" for s, c in top))
        leaders = [s for s, c in top if c == top[0][1]]
        if len(leaders) > 1:
            if pk:
                self.emit("judge", "警上PK再次平票，警徽流失。")
                return
            self.emit("judge", "、".join(f"{s}号" for s in leaders) + "平票，进入警上PK。")
            pk_order = [self.p(x) for x in leaders]
            for s in leaders:
                self.speak(self.p(s), self.round_info(pk_order, self.p(s), "PK发言") + "你进入了警上PK，轮到你发言。", "sheriff_pk")
            self.sheriff_vote([self.p(s) for s in leaders], voters, pk=True)
            return
        self.set_sheriff(leaders[0])
        self.emit("judge", f"{self.sheriff}号当选警长。")

    def pass_badge(self, p, can_speak):
        opts = self.seats(self.alive()) + [0]
        d = self.act(p, "你是警长，出局了。要把警徽移交给谁？target 填座位号，0 表示撕掉警徽。"
                        + ("speech 是移交时说的话。" if can_speak else "你现在不能说话，speech 留空。"), opts, "警徽流失")
        if d is None:
            self.set_sheriff(None)
            self.emit("judge", f"{p.seat}号警长没在时限内移交，警徽流失。")
            return
        t = d["target"]
        sp = d["speech"] if can_speak else ""
        if t:
            self.set_sheriff(t)
            self.emit("badge", sp or f"警徽给{t}号。", p, t)
            self.emit("judge", f"警徽移交给{t}号。")
        else:
            self.set_sheriff(None)
            self.emit("badge", sp or "撕警徽。", p)
            self.emit("judge", "警徽被撕掉，之后没有警长。")

    def speak(self, p, task, typ):
        """游戏内发言：思考（阴时间）+ 发言（阳时间）。思考超过 THINK_SECONDS 的部分从发言时间里扣，全部用完就过麦"""
        total = THINK_SECONDS + SPEECH_SECONDS
        d = self.ask(p, task + SPEECH_RULE, think_limit=None if self.brain.mock else total)
        think = d.get("_think") or 0
        if d.get("_offline"):
            self.emit("judge", f"{p.seat}号掉线了，过麦。")
            return
        if d.get("_timeout"):
            self.emit("judge", f"{p.seat}号思考超时，{total // 60} 分钟内没有开口，过麦。")
            return
        over = max(0, think - THINK_SECONDS)
        speak_sec = SPEECH_SECONDS - over
        if over > 0:
            print(f"  （{p.seat}号 {p.name} 思考了 {think:.0f} 秒，超出 {over:.0f} 秒，发言时间只剩 {speak_sec:.0f} 秒）")
        self.say(typ, d["speech"], p, speak_sec, delay=over)

    def say(self, typ, text, p, speak_sec=None, delay=0):
        """开麦发言：超过可用发言时间（按配音语速折算字数）就掐麦；思考拖延了的，发言前加省略号"""
        limit = int((SPEECH_SECONDS if speak_sec is None else speak_sec) * CHARS_PER_SECOND)
        prefix = "……" if delay > 0 else ""
        if len(text) <= limit:
            self.emit(typ, prefix + text, p)
            if delay:
                self.events[-1]["delay"] = round(delay)
            return
        cut = text[:limit]
        for mark in "。！？；，":  # 尽量在一句话中间偏后的标点处断开，听起来像被打断
            k = cut.rfind(mark)
            if k > limit * 0.6:
                cut = cut[:k + 1]
                break
        self.emit(typ, prefix + cut + "——", p)
        if delay:
            self.events[-1]["delay"] = round(delay)
        self.emit("judge", f"{p.seat}号发言时间到，掐麦。")

    def set_sheriff(self, seat):
        self.sheriff = seat
        self.emit("sheriff", "", None, seat)

    def eliminate(self, p, cause, last_words, announce=True):
        p.alive = False
        if announce:
            self.emit("death", "", p)
        shot = None
        if last_words:
            self.speak(p, "你出局了，请发表遗言。", "last_words")
        if self.sheriff == p.seat:
            self.pass_badge(p, can_speak=last_words)
        if p.role == HUNTER and cause != "poison":
            opts = self.seats(self.alive()) + [0]
            d = self.act(p, "你是猎人，可以开枪带走一人。target 填座位号，填 0 表示不开枪。speech 是开枪时说的话。", opts, "不开枪")
            t = 0 if d is None else d["target"]
            if d is None:
                d = {"speech": "（没来得及开枪）"}
            self.emit("reveal", HUNTER, p)  # 开不开枪都会亮出猎人身份
            if t:
                self.emit("hunter", d["speech"] or f"我是猎人，带走{t}号！", p, t)
                self.emit("judge", f"{t}号被猎人带走。")
                self.p(t).alive = False
                self.emit("death", "", self.p(t))
                shot = self.p(t)
            else:
                self.emit("hunter", d["speech"] or "我是猎人，这枪不开了。", p)
        # 出局采访已取消（太拖时间）。想恢复的话把 INTERVIEWS 改成 True
        if INTERVIEWS:
            self.interview(p)
        if shot:
            self.eliminate(shot, "hunter", last_words=False, announce=False)

    def interview(self, p):
        """出局后的场下采访：不进任何玩家的记录，也不进正片记录，单独存到 interviews/ 里。
        在后台进行，游戏不等它，采访回来再把内容填进去。"""
        ev = {"i": len(self.interviews) + 1, "day": self.day, "phase": self.phase, "type": "interview",
              "seat": p.seat, "name": p.name, "role": p.role, "voice": p.voice,
              "speech": "", "target": None, "public": False, "audience": [p.seat]}
        self.interviews.append(ev)
        if self.brain.mock:
            ev["speech"] = self.ask(p, INTERVIEW_TASK)["speech"]
            return
        system, user = self.system_prompt(p), self.user_prompt(p, INTERVIEW_TASK)  # 按出局那一刻的局面提问

        def work():
            try:
                d = self.brain.ask(p, system, user, None, deadline=time.time() + 600)
            except Exception:
                d = None
            ev["speech"] = str((d or {}).get("speech") or "（这段采访没录上）")
            print(f"\n  🎤 [场外采访] {p.seat}号{p.name}（{p.role}）：{ev['speech']}\n", flush=True)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        self._interviews.append(t)
        print(f"  🎤 {p.seat}号 {p.name} 去场外接受采访了（后台进行，游戏继续）", flush=True)

    def vote(self, candidates=None):
        pk = candidates is not None
        opts_all = candidates if pk else self.seats(self.alive())
        voters = [q for q in self.alive() if q.can_vote and not (pk and q.seat in candidates)]
        task = (f"PK 投票：在{'、'.join(f'{s}号' for s in candidates)}中投一个。" if pk
                else "投票时间。") + "target 填座位号，0 表示弃票。speech 留空。"
        # 大家同时投票：一起问，收齐再公布
        task += f"你有 {DECIDE_SECONDS} 秒（大约 40 秒思考、20 秒操作），超时算弃票。"
        answers = self.ask_all(voters, lambda v: (task, [x for x in opts_all if x != v.seat] + [0]), "投票", {"target": 0})
        results = [(v, d["target"], d.get("timeout")) for v, d in zip(voters, answers)]
        tally = Counter()
        for v, t, late in results:
            w = 1.5 if v.seat == self.sheriff else 1
            note = "（警长1.5票）" if w == 1.5 and t else ""
            self.emit("vote", (f"投{t}号" if t else ("弃票（超时）" if late else "弃票")) + note, v, t or None)
            if t:
                tally[t] += w

        if not tally:
            self.emit("judge", "无人得票，今天没有人出局。")
            return
        top = tally.most_common()
        leaders = [s for s, c in top if c == top[0][1]]
        self.emit("judge", "票型：" + "，".join(f"{s}号{c:g}票" for s, c in top))
        if len(leaders) > 1:
            if pk:
                self.emit("judge", "再次平票，今天没有人出局。")
                return
            self.emit("judge", "、".join(f"{s}号" for s in leaders) + "平票，进入PK。")
            pk_order = [self.p(x) for x in leaders]
            for s in leaders:
                self.speak(self.p(s), self.round_info(pk_order, self.p(s), "PK发言") + "你进入了PK，轮到你发言。", "pk_speech")
            self.vote(candidates=leaders)
            return

        out = self.p(leaders[0])
        self.emit("judge", f"{out.seat}号被放逐。")
        if out.role == IDIOT and not out.idiot_revealed:
            out.idiot_revealed, out.can_vote = True, False
            self.emit("reveal", IDIOT, out)
            self.emit("judge", f"{out.seat}号翻牌，身份是白痴，免于出局，但之后不能投票。")
            if self.sheriff == out.seat:
                self.set_sheriff(None)
                self.emit("judge", "白痴警长翻牌，警徽流失。")
            return
        self.eliminate(out, "vote", last_words=True)

    # ---------- 导出 ----------
    def save(self, out_dir, wait=True):
        pending = [t for t in self._interviews if t.is_alive()]
        if pending and wait:
            print(f"\n等 {len(pending)} 段场外采访录完再保存……")
            for t in pending:
                t.join(timeout=600)
        os.makedirs(out_dir, exist_ok=True)
        players = [{"seat": q.seat, "name": q.name, "model": q.model, "role": q.role,
                    "voice": q.voice, "alive": q.alive} for q in self.ps]
        with open(os.path.join(out_dir, "log.json"), "w", encoding="utf-8") as f:
            json.dump({"winner": self.winner, "players": players, "plans": getattr(self, "plans", {}), "events": self.events},
                      f, ensure_ascii=False, indent=2)

        lines = ["# AI 狼人杀 · 对局剧本（上帝视角）", "", f"**结果：{result_text(self.winner)}**", ""]
        lines += role_table(players)
        lines += render_events([e for e in self.events if e["type"] not in ("setup", "plan")], show_roles=True)
        with open(os.path.join(out_dir, "script.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        if self.interviews:
            iv_dir = os.path.join(out_dir, "interviews")
            os.makedirs(iv_dir, exist_ok=True)
            with open(os.path.join(iv_dir, "interviews.json"), "w", encoding="utf-8") as f:
                json.dump({"winner": self.winner, "players": players, "events": self.interviews},
                          f, ensure_ascii=False, indent=2)
            lines = ["# AI 狼人杀 · 出局采访（场下，只有观众能看到）", "",
                     "按出局顺序排列，要用哪段就剪进正片对应的位置。", ""]
            lines += render_events(self.interviews, show_roles=True)
            with open(os.path.join(iv_dir, "interviews.md"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines))


def result_text(winner):
    return f"{winner}阵营胜利" if winner else "未分胜负"


def role_table(players):
    lines = ["| 座位 | 名字 | 模型 | 身份 |", "|---|---|---|---|"]
    lines += [f"| {q['seat']} | {q['name']} | {q['model']} | {q['role']} |" for q in players]
    return lines


def render_events(events, show_roles, known=None):
    """把事件排成剧本。show_roles=False 时，只显示 known 里的座位的身份。"""
    lines, section = [], None
    for e in events:
        if e["type"] in STATE_EVENTS:
            continue
        sec = "开局" if e["day"] == 0 else f"第{e['day']}{e['phase']}"
        if e.get("section"):
            sec = e["section"]
        if sec != section:
            section = sec
            lines += ["", f"## {sec}", ""]
        label = TYPE_LABEL.get(e["type"], e["type"])
        if e["seat"]:
            role = e["role"] if show_roles or (known and e["seat"] in known) else None
            who = f"{e['seat']}号 {e['name']}" + (f"（{role}）" if role else "")
        else:
            who = "法官"
        mark = " 🎤" if e["type"] == "interview" else ("" if e["public"] else " 🔒")
        lines.append(f"**[{label}{mark}] {who}**：{e['speech']}")
        lines.append("")
    return lines


def pick_seat(players, who):
    if who is None or who == "random":
        return random.choice(players)["seat"]
    if str(who).isdigit():
        seat = int(who)
        if not 1 <= seat <= len(players):
            raise SystemExit(f"座位号要在 1～{len(players)} 之间")
        return seat
    seats = [q["seat"] for q in players if q["role"] == who]
    if not seats:
        raise SystemExit(f"这局里没有身份是「{who}」的玩家")
    return random.choice(seats)


def export_pov(log_path, who):
    with open(log_path, encoding="utf-8") as f:
        d = json.load(f)
    players, events = d["players"], d["events"]
    if events and "audience" not in events[0]:
        raise SystemExit("这份 log.json 是旧版程序生成的，没有记录“谁知道”，请用新版重新打一局")
    seat = pick_seat(players, who)
    me = players[seat - 1]

    known = {seat}
    for e in events:  # 狼人开局就知道队友
        if e["type"] == "setup" and e["seat"] == seat and me["role"] == WOLF:
            known |= {q["seat"] for q in players if q["role"] == WOLF}
    shown = [e for e in events if e["audience"] == "all" or seat in e["audience"]]

    out_dir = os.path.dirname(log_path)
    tag = f"pov{seat}"
    with open(os.path.join(out_dir, f"log_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump({"winner": d["winner"], "pov_seat": seat, "pov_role": me["role"],
                   "players": players, "events": shown}, f, ensure_ascii=False, indent=2)

    lines = [f"# AI 狼人杀 · {seat}号 {me['name']} 的视角（{me['role']}）", "",
             "视角玩家只看到他自己能知道的内容；出局后也一样，只看公开内容（面杀规则）。", ""]
    # 正片只显示视角玩家知道的身份，结尾的结果表显示全部身份
    lines += render_events(shown, show_roles=False, known=known)
    lines += ["", f"## 结果", "", f"**{result_text(d['winner'])}**", ""] + role_table(players)
    path = os.path.join(out_dir, f"script_{tag}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"已导出 {seat}号（{me['role']}）视角：{path}")


def strip_effort(p):
    """去掉思考强度相关参数，返回是否真的去掉了什么"""
    removed = False
    for attr in ("extra_body", "quick_extra_body"):
        body = getattr(p, attr)
        if body:
            new = {k: v for k, v in body.items() if k not in ("reasoning_effort", "thinking")}
            if new != body:
                setattr(p, attr, new or None)
                removed = True
    return removed


def check_players(players):
    """给每个座位发一句话，确认模型名、地址、key 都能用"""
    from openai import OpenAI
    ok = 0
    for q in players:
        t0 = time.time()
        try:
            cli = OpenAI(base_url=q.base_url, api_key=os.environ[q.api_key_env], timeout=q.timeout, max_retries=0)
            kw = {} if q.temperature is None else {"temperature": q.temperature}
            if q.extra_body:
                kw["extra_body"] = q.extra_body
            msgs = [{"role": "user", "content": '只回复这个 JSON，不要别的：{"speech": "到"}'}]
            note = ""
            try:
                r = cli.chat.completions.create(model=q.model, messages=msgs, **kw)
            except Exception as e:
                if getattr(e, "status_code", None) == 400 and any(k in str(e).lower() for k in ("reasoning", "thinking", "effort")) and strip_effort(q):
                    kw.pop("extra_body", None)
                    if q.extra_body:
                        kw["extra_body"] = q.extra_body
                    r = cli.chat.completions.create(model=q.model, messages=msgs, **kw)
                    note = "（不支持思考强度参数，对局时会自动去掉）"
                else:
                    raise
            effort = (q.extra_body or {}).get("reasoning_effort", "默认")
            txt = (r.choices[0].message.content or "").strip().replace("\n", " ")
            print(f"  ✅ {q.seat:>2}号 {q.name:<14} {q.model:<22} 强度:{effort:<6} {time.time() - t0:5.1f}秒  回复：{txt[:30]}{note}")
            ok += 1
        except Exception as e:
            print(f"  ❌ {q.seat:>2}号 {q.name:<14} {q.model:<22} 失败：{str(e)[:160]}")
    print(f"\n{ok}/{len(players)} 个座位可用" + ("，可以开打了！" if ok == len(players) else "，把失败的修好再开打。"))


def load_keys(path):
    """读取 keys.txt（每行 名字=key），填进环境变量"""
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v:
                os.environ[k] = v
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="AI 狼人杀 · 自动法官")
    ap.add_argument("--config", default="players.json", help="玩家配置文件")
    ap.add_argument("--mock", action="store_true", help="不调 API，随机发言，用来测流程")
    ap.add_argument("--seed", type=int, default=None, help="随机种子（决定身份分配）")
    ap.add_argument("--max-days", type=int, default=10)
    ap.add_argument("--out", default="out")
    ap.add_argument("--export-pov", metavar="LOG", help="从已打完的 log.json 导出第一视角")
    ap.add_argument("--seat", default="random", help="视角玩家：座位号、身份名（如 女巫/村民）或 random")
    ap.add_argument("--check", action="store_true", help="不打游戏，只测试每个座位的模型能不能调通")
    ap.add_argument("--split", default="", help="让这几组玩家分属不同阵营，按名字匹配，如 Claude,GPT")
    args = ap.parse_args()

    if args.export_pov:
        export_pov(args.export_pov, args.seat)
        return

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    if len(cfg["players"]) != 12:
        raise SystemExit("players.json 里需要正好 12 个玩家")
    allowed = {"name", "model", "base_url", "api_key_env", "voice", "style", "temperature", "timeout", "extra_body", "stream",
               "quick_extra_body", "short"}
    players = [Player(seat=i + 1, fixed_role=pc.get("role", ""), **{k: v for k, v in pc.items() if k in allowed})
               for i, pc in enumerate(cfg["players"])]
    for q, pc in zip(players, cfg["players"]):
        if "temperature" not in pc and "kimi" in q.model.lower():
            q.temperature = 1  # Kimi 只接受 temperature=1
        if "quick_extra_body" not in pc:
            q.quick_extra_body = next((v for k, v in QUICK_DEFAULTS if k in q.model.lower()), None)
        if "extra_body" not in pc:
            q.extra_body = dict(next((v for k, v in EFFORT_DEFAULTS if k in q.model.lower()), EFFORT_DEFAULT))

    if not args.mock:
        kp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys.txt")
        if not os.path.exists(kp) and not os.environ.get(players[0].api_key_env):
            raise SystemExit("没找到 keys.txt：把 keys.example.txt 复制一份、改名为 keys.txt，再把各家的 API key 填进去")
        load_keys(kp)
        missing = sorted({q.api_key_env for q in players if not os.environ.get(q.api_key_env)})
        if missing:
            raise SystemExit("keys.txt 里这些 key 还没填：" + "、".join(missing))
        try:
            import openai  # noqa: F401
        except ImportError:
            raise SystemExit("先安装依赖：pip install openai")

    if args.check:
        if args.mock:
            raise SystemExit("--check 用来测真实 API，不要和 --mock 一起用")
        check_players(players)
        return

    if args.seed is not None:
        random.seed(args.seed)
    out_dir = os.path.join(args.out, time.strftime("%Y%m%d-%H%M%S"))
    game = Game(players, Brain(mock=args.mock))
    try:
        game.run(max_days=args.max_days, split=[x.strip() for x in args.split.split(",") if x.strip()] or None,
                 out_dir=out_dir)
    except FatalAPIError as e:
        print(f"\n❌ 对局中止：{e}")
        print("   已经打完的部分会保存下来。修好后用 --check 确认，再重新开一局。")
    except KeyboardInterrupt:
        print("\n⏹ 手动停止，保存已经打完的部分……")
    finally:
        game.save(out_dir)
        print(f"\n对局记录已保存到 {out_dir}/（log.json、script.md）")


if __name__ == "__main__":
    main()
