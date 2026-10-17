# research-paper-style

**科研论文式作答风格**：每次回答先给 `## 摘要`（1–3 句、只给结论、首句加粗），再在 `## 详细介绍` 里展开技术参数与过程，文末给「参考文献」；引用本地文件/网页用 `[n]` 标注并写成**可点击溯源链接**（本地文件跳到指定行）。核心原则：**结论先行、证据可查、严禁编造**。

> 附带一个可选的 DSH 插件 `dsh-cite-style`：把风格注入每一轮系统提示，并提供一个只读的溯源预览路由 `/dsh-cite/source`（点击 `[n]` 打开源文并高亮行；文件不存在时明确提示"可能是编造的引用"）。

---

## 目录结构

```
research-paper-style/
├── SKILL.md                 # 技能本体（agent skill；规则块由生成器维护）
├── style.policy.yaml        # 规则的唯一来源（结构/摘要/引用/输出形态/隐私/语气）
├── tools/
│   ├── gen_style.py         # 从策略生成：plugin/style.prompt.mjs + SKILL.md 规则块
│   └── check_answer.py      # 对一条回答做 lint（10 项）
├── examples/golden/         # 4 条黄金用例（2 通过 / 2 应报错）
└── plugin/                  # 可选：DSH 插件（dsh-cite-style）
    ├── index.js             # 注入提示段 + /dsh-cite/source 只读路由
    ├── style.prompt.mjs     # 生成物：STYLE_PROMPT + 敏感名黑名单
    ├── cordis.patch.yml     # 插件行（插入 id: dsh-cite-style）
    └── package.json
```

## 快速开始

### 1) 只用技能（任何支持 Agent Skills 的客户端）

```bash
cp -r . ~/.agents/skills/research-paper-style     # 或你的技能目录
```

然后把 `SKILL.md` 里的规则视作作答规范。注意：`[n]` 的**可点击**依赖插件路由；没有插件时 `[n]` 退化为纯文本标注（写作纪律不变）。

### 2) 装 DSH 插件（可选，获得"可点击溯源"）

```powershell
dsh plugin --profile desktop add "<本仓库路径>\plugin"
# 重启 DSH 后：每轮自动注入风格；点击 [n] 打开 /dsh-cite/source 预览页
```

插件零第三方依赖，只用宿主服务：`ctx.systemPrompt.section(...)` 注入提示段、`ctx.webServer.register(...)` 注册只读路由；无 web 服务的 composition（如 TUI）会自动跳过路由、只保留风格。

## 规则（`style.policy.yaml` 摘要）

| 段 | 关键约束 |
|---|---|
| `structure` | 全文仅三个二级标题：`## 摘要` / `## 详细介绍` / `## 参考文献`；详细介绍内部一律 `###` |
| `abstract` | ≤3 句、只给结论；**首句＝直接答案并加粗**；改动文件用**行内代码**写文件名（工作区内可点 chip，工作区外改链接）；禁止在摘要里放尺寸/格式/依赖/过程/自检/绝对路径 |
| `citations` | `[n]` 递增；本地文件用 `/dsh-cite/source?path=…&line=…`；外部 URL 直链；**引用前必须真读过**；标注证据强度 `[强]/[中]/[弱]`；外部来源须含标题/站点/访问日期 |
| `outputs` | GUI＝可点链接；TUI＝`路径:行号`；导出 Markdown＝相对路径+脚注；粘贴 IM＝文件名+一句话来源 |
| `privacy` | 敏感文件名黑名单（`.ssh`/`id_rsa`/`.pem` 等）在路由层直接 403；外发时不留盘符 |

## 工具链

```bash
# 改完 style.policy.yaml 后：重新生成「提示段 + SKILL.md 规则块」
python tools/gen_style.py

# 一致性回归：两处产物是否与策略一致（不写盘）
python tools/gen_style.py --check

# 对一条回答做 lint（10 项：结构/句数/首句加粗/禁用内容/绝对路径/链接标签/内部 ##）
python tools/check_answer.py answer.md
```

**黄金用例**：`pass-01/02` 应全绿；`fail-01`（未加粗 + 禁用词 + 绝对路径）、`fail-02`（多出 `##`）应各自报错。

## 已知限制

- 行号是否准确取决于**是否真的读过该文件**；路由能抓"文件不存在"这类硬编造，但"行号对、内容不对"仍需人看一眼预览页；
- **可点击 chip 只对工作区内文件有效**（DSH 的 `openFile` 有工作区边界）；工作区外文件请用链接或镜像到工作区；
- 插件提示段是字符串常量：**改策略后需重启 DSH**；技能文件即时生效。

## English (short)

`research-paper-style` is an agent skill that makes answers **abstract-first**: a `## 摘要` of 1–3 bold-lead sentences, then `## 详细介绍` with parameters and process, then a references list. Citations are numbered `[n]` and rendered as clickable links that open the exact source line (via the optional DSH plugin route `/dsh-cite/source`). Rules live in `style.policy.yaml`; `tools/gen_style.py` generates both the injected prompt and the skill's rules block, and `tools/check_answer.py` lints an answer against the policy.

## License

MIT —— see [LICENSE](./LICENSE).
