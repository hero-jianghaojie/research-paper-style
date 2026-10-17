#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对一条回答做「科研论文式」lint。用法：
    python tools/check_answer.py answer.md            # 检查文件
    python tools/check_answer.py --stdin < answer.md  # 从 stdin 读
退出码：0 全部通过；1 有失败项。
规则来源于 style.policy.yaml（若缺失则用内置默认）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "max_sentences": 3,
    "bold_first": True,
    "require_file_links": True,
    "forbid": ["800×600", "纯矢量", "无外部字体", "迭代", "改了几轮", "自检"],
    "abs_path": re.compile(r"\b[EC]:[\\/]", re.I),
}


def load() -> dict:
    p = ROOT / "style.policy.yaml"
    if not p.exists():
        return DEFAULTS
    try:
        import yaml  # type: ignore
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return DEFAULTS
    ab = (d.get("abstract") or {})
    return {
        "max_sentences": int(ab.get("max_sentences", 3)),
        "bold_first": bool(ab.get("bold_first_sentence", True)),
        "require_file_links": bool(ab.get("require_file_links", True)),
        "forbid": list(ab.get("forbid_tokens") or ab.get("forbid_in_abstract") or DEFAULTS["forbid"]),
        "abs_path": DEFAULTS["abs_path"],
    }


def split_sections(text: str):
    """返回 (abstract, detail, refs) 三段文本；缺失的为 None。
    注意：detail 一直截到「## 参考文献」为止，这样内部若混入 `##` 才能被检出。"""
    m = re.search(r"^##\s*摘要\s*$(.*?)(?=^##\s*详细介绍|^##\s*参考文献|\Z)", text, re.S | re.M)
    d = re.search(r"^##\s*详细介绍\s*$(.*?)(?=^##\s*参考文献|\Z)", text, re.S | re.M)
    r = re.search(r"^##\s*参考文献\s*$(.*)\Z", text, re.S | re.M)
    return (m.group(1) if m else None, d.group(1) if d else None, r.group(1) if r else None)


def count_sentences(s: str) -> int:
    t = re.sub(r"\[[^\]]*\]\([^)]*\)", "", s)      # 去链接
    t = re.sub(r"`[^`]*`", "", t)                   # 去行内代码
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    parts = [x for x in re.split(r"[。！？!?]+", t) if x.strip()]
    return len(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--stdin", action="store_true")
    args = ap.parse_args()
    text = sys.stdin.read() if args.stdin else Path(args.file).read_text(encoding="utf-8")
    cfg = load()

    abstract, detail, refs = split_sections(text)
    checks: list[tuple[str, bool, str]] = []

    checks.append(("首行为 ## 摘要", bool(re.match(r"^\s*##\s*摘要\s*$", text, re.M)), ""))
    heads = re.findall(r"^##\s+(\S[^\n]*?)\s*$", text, re.M)
    checks.append(("二级标题恰为 摘要/详细介绍/参考文献（顺序一致）",
                   heads == ["摘要", "详细介绍", "参考文献"],
                   f"实际: {heads}"))
    checks.append(("存在 ## 详细介绍", detail is not None, ""))
    checks.append(("存在 ## 参考文献", refs is not None, ""))

    if abstract is not None:
        n = count_sentences(abstract)
        checks.append((f"摘要 ≤ {cfg['max_sentences']} 句（实际 {n}）", n <= cfg["max_sentences"], ""))
        first_para = re.split(r"\n\s*\n", abstract.strip())[0]
        # 先去链接再切句：URL 里的 "?" 会误当句末标点
        para_wo_links = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", first_para)
        first_sent = re.split(r"[。！？!?]", para_wo_links)[0]
        has_bold = first_sent.count("**") >= 2
        checks.append(("摘要首句加粗", has_bold or not cfg["bold_first"], ""))
        hits = [w for w in cfg["forbid"] if w in abstract]
        checks.append(("摘要未含禁用内容", not hits, f"命中: {hits}" if hits else ""))
        checks.append(("摘要未出现绝对路径", not cfg["abs_path"].search(abstract), ""))
        if cfg["require_file_links"]:
            links = re.findall(r"\[([^\]]+)\]\(([^)]*dsh-cite[^)]*)\)", abstract)
            bad = [lab for lab, _ in links if re.search(r"[EC]:[\\/]", lab)]
            checks.append(("链接标签不含路径", not bad, f"标签: {bad}" if bad else ""))

    if detail is not None:
        checks.append(("详细介绍内部无 ## 小节", not re.search(r"^##\s", detail, re.M), ""))

    ok = True
    for name, passed, extra in checks:
        mark = "✅" if passed else "❌"
        print(f"  {mark} {name}" + (f"  ({extra})" if extra and not passed else ""))
        ok &= passed
    print(f"\n{'✅ 全部通过' if ok else '❌ 存在失败项'}（{sum(1 for _, p, _ in checks if p)}/{len(checks)}）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
