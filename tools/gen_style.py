#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 style.policy.yaml 生成两处产物：
  1) style.prompt.mjs —— 插件注入的提示段（index.js 直接 import）
  2) SKILL.md 中 STYLE:RULES 标记之间的规则块（其余内容保持手写）
用法：python tools/gen_style.py [--check]
      --check 只校验两处产物是否与策略一致（不写盘），不一致时退出码 1。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "style.policy.yaml"
# 注入产物：优先放 plugin/ 下（与 index.js 同目录，便于相对 import）；也可用 STYLE_PROMPT_OUT 指定。
PROMPT = Path(os.environ.get("STYLE_PROMPT_OUT", str(
    (ROOT / "plugin" / "style.prompt.mjs") if (ROOT / "plugin").is_dir() else (ROOT / "style.prompt.mjs")
)))
# 技能文件：优先仓库根的 SKILL.md；否则用已安装技能（~/.agents/skills/…）；可用 STYLE_SKILL 指定。
_DEFAULT_SKILL = (ROOT / "SKILL.md") if (ROOT / "SKILL.md").exists() else (
    Path.home() / ".agents" / "skills" / "research-paper-style" / "SKILL.md"
)
SKILL = Path(os.environ.get("STYLE_SKILL", str(_DEFAULT_SKILL)))
BEGIN = "<!-- STYLE:RULES:BEGIN -->"
END = "<!-- STYLE:RULES:END -->"


def load_policy() -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:  # 极简回退：只支持本文件的扁平结构（够用）
        raise SystemExit("需要 PyYAML：pip install pyyaml（或改用 uv run --with pyyaml）")
    return yaml.safe_load(POLICY.read_text(encoding="utf-8"))


def build_prompt(p: dict) -> list[str]:
    st, ab, ci, out, pv, tn = p["structure"], p["abstract"], p["citations"], p["outputs"], p.get("privacy", {}), p["tone"]
    hs = "#" * int(st["heading_level"])
    sub = "#" * int(st["detail_subheading_level"])
    L: list[str] = []
    L.append("【回答风格：科研论文式】（由 dsh-cite-style 插件注入；除用户明确要求其它风格外，始终遵守）")
    L.append("")
    L.append(f"1) 结构（固定）：先从二级标题 `{hs} {st['abstract_heading']}` 起头，下面 1–{ab['max_sentences']} 句只给结论。")
    L.append("   - 只写“做了什么 / 结论是什么”，不铺垫、不寒暄、不写“好的/当然”之类；")
    if ab["bold_first_sentence"]:
        L.append("   - **摘要把「直接回答问题的结论」加粗**（Markdown `**…**`，只加这一处；其余句子不加粗）；")
    if ab["require_file_links"]:
        if ab.get("file_ref_form") == "inline-code":
            L.append("   - **若本轮改了/新建了文件，摘要里必须用行内代码写出文件名**（如 `style.policy.yaml`，DSH 会渲染成可点 chip；仅工作区内文件有效，工作区外改用 /dsh-cite/source 链接），紧跟主题词之后；只读未改则不加；")
        else:
            L.append("   - **若本轮改了/新建了文件，摘要里必须把它们的可点击链接紧跟主题词之后**（标签用文件名）；只读未改则不加链接；")
    L.append("   - 摘要里不要放：" + "、".join(f"（{x}）" for x in ab["forbid_in_abstract"]) + "；")
    L.append("   - 专业术语可用英文原词，但**首次出现必须紧跟中文括注**，例如：power-added efficiency（功率附加效率，PAE）；")
    L.append("   - 数值给单位与量级；不确定的写“约/待验证”，绝不把猜测写成事实。")
    L.append(f"   摘要之后另起一行，写 `{hs} {st['detail_heading']}`，把技术参数、做法与过程、自检结论、文件链接等全部放在这一节展开。")
    if st["only_three_h2"]:
        L.append(f"   层级纪律：全文只允许三个二级标题（`{hs} {st['abstract_heading']}` / `{hs} {st['detail_heading']}` / `{hs} {st['references_heading']}`）；「{st['detail_heading']}」内部的小节一律用 `{sub}`，不得再出现 `{hs}`。")
    L.append("")
    L.append("2) 引用：凡引用 (a) 文献或网页、(b) 用户文件夹里已有的文件内容、(c) 本会话先前给出的定稿数值，都必须用 [n] 标注（n 从 1 递增，同一来源复用同一序号），并写成可点击链接：")
    L.append(f"   - 本地文件：`[n]({ci['local_file_link']})`")
    L.append(f"   - 外部网页：`[n]({ci['external_link']})`")
    L.append("   - 行号只在**确实读过该文件**时给出；没读过就省略 line/end（链接仍会打开文件开头）。")
    if ci.get("require_read_before_cite"):
        L.append("   - 硬闸门：引用某个本地文件前，本轮必须已成功读取过它；否则只写文件名、不写行号，或标注“（未验证）”。")
    if ci.get("evidence_grade"):
        g = "、".join(f"`[{x}]`" for x in ci["grades"])
        L.append(f"   - 证据强度：在参考文献条目标注 {g}（强＝一手/官方文档或本机实测；中＝权威二手；弱＝博客/论坛/未证实）。")
    L.append("")
    L.append(f"3) 文末固定加 `{hs} {st['references_heading']}`，逐条写 `[n] 标题或说明 — 来源`，并再次给出可点击链接；外部来源需含" + "、".join(ci["external_source_fields"]) + "。")
    L.append("")
    L.append("4) 反编造（硬约束）：只引用你确实读到过的内容。严禁虚构文件路径、行号、论文标题、作者、年份、DOI、URL；不确定就标注“（未验证）”或不写。")
    L.append("")
    L.append("5) 语气：" + tn["language"] + ("；不用“" + "/".join(tn["no_hedging_words"]) + "”这类软词" if tn.get("no_hedging_words") else "") + "；不写客套话。")
    L.append("")
    L.append("6) 输出形态：" + "；".join(f"{k}→{v}" for k, v in out.items()) + "。")
    if pv.get("external_mode_hint"):
        L.append(f"   隐私：{pv['external_mode_hint']}")
    em = p.get("emphasis") or {}
    if em:
        forms = em.get("forms") or {}
        if em.get("forbid_html_tags"):
            L.append("7) 强调：**禁止原始 HTML**（`<u>`/`<span>`/`<mark>` 等不会被渲染，会显示成字面标签）；彩色/下划线/高亮**只能用 KaTeX 行内数学**，其余用 Markdown/符号：")
        else:
            L.append("7) 强调：只用下面这套形式：")
        for key, spec in forms.items():
            L.append(f"   - {spec.get('marker','')} {spec.get('style','')}：{spec.get('use','')}（{key}）")
        L.append(f"   每段（空行分隔）最多 {em.get('per_paragraph_limit', 2)} 处强调；颜色/符号**不能是唯一信息载体**，须配文字说明。")
        if em.get("abstract_no_color"):
            L.append("   摘要里不用彩色/高亮（🔴🟠🟢 与 $\\textcolor{}$、$\\colorbox{}$）与删除线——摘要只保留「首句加粗」这一处强调。")
    return L


def build_rules_md(p: dict) -> str:
    st, ab, ci, out, pv, tn = p["structure"], p["abstract"], p["citations"], p["outputs"], p.get("privacy", {}), p["tone"]
    hs = "#" * int(st["heading_level"])
    sub = "#" * int(st["detail_subheading_level"])
    L = [
        f"> ⚠️ 本节由 `tools/gen_style.py` 从 `style.policy.yaml` 生成（策略 v{p['version']}），请勿手改；改策略后重跑生成器。",
        "",
        "## 输出结构（固定）",
        "",
        f"1. **`{hs} {st['abstract_heading']}`——1–{ab['max_sentences']} 句，只给结论**",
        f"   {'- **首句＝直接回答问题的结论，必须加粗（只加粗这一处）**' if ab['bold_first_sentence'] else ''}",
        f"   {'- **本轮改了/新建文件时，用行内代码写出文件名紧跟主题词之后**（如 `style.policy.yaml`，DSH 渲染成可点 chip；仅工作区内有效，工作区外改链接）' if ab['require_file_links'] and ab.get('file_ref_form') == 'inline-code' else ('- **本轮改了/新建文件时，这些文件的链接紧跟主题词之后**（标签用文件名）' if ab['require_file_links'] else '')}",
        "   - 摘要里不要放：" + "、".join(ab["forbid_in_abstract"]) + "。",
        "   - 英文术语首次出现带中文括注；不确定写「约/待验证」。",
        f"2. **`{hs} {st['detail_heading']}`**：技术参数（尺寸/格式/依赖/行号）、做法与过程、自检结论、文件链接，全部放这里。",
    ]
    if st["only_three_h2"]:
        L.append(f"   - **层级纪律**：全文只允许三个二级标题（`{hs} {st['abstract_heading']}` / `{hs} {st['detail_heading']}` / `{hs} {st['references_heading']}`）；内部小节**一律用 `{sub}`**。")
    L += [
        f"3. 文末固定 `{hs} {st['references_heading']}`。",
        "",
        "## 引用规则",
        "",
        "| 来源类型 | 写法 |",
        "|---|---|",
        f"| 本地文件 | `[n]({ci['local_file_link']})` |",
        f"| 外部网页 | `[n]({ci['external_link']})` |",
        "",
        ("- **硬闸门**：引用本地文件前必须真正读取过；没读过就省略 `line`/`end`，或标「（未验证）」。" if ci.get("require_read_before_cite") else ""),
        (f"- **证据强度**：" + "、".join(f"`[{x}]`" for x in ci["grades"]) + "（强＝一手/官方/本机实测；中＝权威二手；弱＝博客/论坛）。" if ci.get("evidence_grade") else ""),
        (f"- 外部来源须含：" + "、".join(ci["external_source_fields"]) + "。" if ci.get("require_access_date") else ""),
        "",
        "## 输出形态矩阵",
        "",
        "| 场景 | 输出 |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in out.items()],
        "",
        f"> 隐私：{pv.get('external_mode_hint', '')}（敏感文件名黑名单：{', '.join(pv.get('sensitive_name_patterns', []))}）。",
        "",
        "## 语气",
        "",
        f"- {tn['language']}；不写客套话；不用「" + "、".join(tn.get("no_hedging_words", [])) + "」这类软词。",
    ]
    em = p.get("emphasis") or {}
    if em:
        L += ["", "## 强调体系（只许这些形式）", ""]
        if em.get("forbid_html_tags"):
            L.append("> ⚠️ **禁止原始 HTML**：DSH 的 Markdown 渲染器没有 rehype-raw，`<u>`/`<span>`/`<mark>` 会显示成字面标签。")
            L.append("")
        L += ["| 语义 | 形式 | 用在哪 |", "|---|---|---|"]
        for key, spec in (em.get("forms") or {}).items():
            L.append(f"| {spec.get('marker','')} | {spec.get('style','')} | {spec.get('use','')} |")
        L += ["", f"- 每段（空行分隔）最多 **{em.get('per_paragraph_limit', 2)}** 处强调；颜色/符号不是唯一信息载体。"]
        if em.get("abstract_no_color"):
            L.append("- **摘要里不用颜色符号与删除线**，只保留首句加粗。")
        for ex in (em.get("examples") or []):
            L.append(f"- 例：{ex}")
    return "\n".join(x for x in L)


def render_prompt_mjs(lines: list[str], policy_text: str, deny: list[str]) -> str:
    digest = hashlib.sha256(policy_text.encode("utf-8")).hexdigest()[:12]
    body = ",\n".join("  " + repr(x) for x in lines)
    return (
        "// AUTO-GENERATED by tools/gen_style.py from style.policy.yaml —— 勿手改。\n"
        f"// policy-sha256: {digest}\n"
        f"export const STYLE_PROMPT = [\n{body},\n].join('\\n')\n"
        "\n// 敏感文件名黑名单（路由拒绝预览）\n"
        f"export const DENY_PATTERNS = {deny!r}\n".replace("'", '"')
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    p = load_policy()
    lines = build_prompt(p)
    deny = (p.get("privacy", {}) or {}).get("sensitive_name_patterns", []) or []
    text = render_prompt_mjs(lines, POLICY.read_text(encoding="utf-8"), deny)
    rules = build_rules_md(p)

    # SKILL.md：替换标记之间的块；若标记缺失，则把「输出结构…」到「## 反编造」之间自动包起来
    skill = SKILL.read_text(encoding="utf-8")
    if BEGIN not in skill or END not in skill:
        start = skill.find("## 输出结构（固定）")
        stop = skill.find("## 反编造")
        if start < 0 or stop < 0 or stop <= start:
            print(f"❌ SKILL.md 既无标记 {BEGIN}，也找不到可包裹的「输出结构→反编造」区间")
            return 2
        skill = skill[:start] + f"{BEGIN}\n{END}\n\n" + skill[stop:]
        SKILL.write_text(skill, encoding="utf-8")
        print("ℹ️ 已自动插入 STYLE:RULES 标记")
    new_skill = re.sub(
        re.escape(BEGIN) + r".*?" + re.escape(END),
        lambda _: f"{BEGIN}\n\n{rules}\n\n{END}",
        skill,
        flags=re.S,
    )

    if args.check:
        ok = PROMPT.exists() and PROMPT.read_text(encoding="utf-8") == text and new_skill == skill
        print(("✅ 两处产物与策略一致" if ok else "❌ 产物与策略不一致，请运行 tools/gen_style.py"))
        return 0 if ok else 1

    PROMPT.write_text(text, encoding="utf-8")
    if new_skill != skill:
        SKILL.write_text(new_skill, encoding="utf-8")
        print("✅ 已更新 SKILL.md 规则块")

    # 工作区镜像（可选）：DSH 的文件 chip 只能打开「工作区内」的文件；设置
    # CITE_STYLE_MIRROR 后把策略同步到该目录，摘要里就能用行内代码生成可点 chip。
    mirror_env = os.environ.get("CITE_STYLE_MIRROR", "")
    mirror_dir = Path(mirror_env) if mirror_env else None
    if mirror_dir is not None and mirror_dir.is_dir():
        mirror = mirror_dir / "style.policy.yaml"
        src_text = POLICY.read_text(encoding="utf-8")
        if not mirror.exists() or mirror.read_text(encoding="utf-8") != src_text:
            mirror.write_text(src_text, encoding="utf-8")
            print(f"✅ 已同步工作区镜像：{mirror}")
        else:
            print(f"✅ 工作区镜像已是最新：{mirror}")
    elif mirror_dir is not None:
        print(f"ℹ️ 工作区镜像目录不存在，跳过：{mirror_dir}")

    print(f"✅ 已生成 {PROMPT.name}（{len(lines)} 行，{len(text)} 字符）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
