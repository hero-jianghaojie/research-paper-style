# dsh-cite-style

**科研论文式回答风格 + 可点击引用溯源**（DSH 插件）。

回答时先给一段**中文 IEEE 论文摘要风格**的结论，再展开详细论述；论述中引用「文献 / 网页 / 你文件夹里已有的文件」时用 **[n]** 标注，并且 **`[n]` 是可点击的**——点开即跳到**源文位置**（本地文件会高亮被引用的行；网页则直接打开 URL）。

> 设计底线：**宁可少写，也不编造**。引用的来源打不开时，预览页会直接告诉你「这条引用可能是编造的」，供你一眼核验。

---

## 它做了什么

| 半边 | 行为 |
|---|---|
| **提示段**（`ctx.systemPrompt.section`） | 注入「回答风格契约」：摘要式结论 → 详细论述 → 参考文献；中文书面语；英文术语首次出现加中文括注；`[n]` 引用格式固定；**禁止虚构路径/行号/文献**。 |
| **只读预览路由**（`ctx.webServer.register`） | `GET /dsh-cite/source?path=<绝对路径>&line=<起始行>&end=<结束行>&title=<标题>`：显示文件、行号、上下文，并**高亮引用行**。文件不存在 → 明确显示「可能是编造的引用」。 |

`[n]` 之所以能点击，是因为模型被要求把它写成**普通 Markdown 链接**指向该路由——不依赖任何前端 JS，因此在 Web GUI、TUI（无路由时降级为纯文本 `[n]`）都能用。

## 引用格式（模型输出示例）

```markdown
[1](/dsh-cite/source?path=E%3A%5CAI%5CautoADS%5CREADME.md&line=12&end=18)
[2](https://arxiv.org/abs/2401.00001)
```

文末「参考文献」再列一次同样的链接，便于核对：

```markdown
## 参考文献
[1] autoADS 说明 — `E:\AI\autoADS\README.md`（第 12–18 行）
[2] 某论文 — https://arxiv.org/abs/2401.00001
```

## 安装

```powershell
# 1) 装入 desktop profile（本地目录方式；也可 npm 安装后引用包名）
dsh plugin --profile desktop add "C:\Users\30671\.dsh\plugins-src\dsh-cite-style"
# 2) 重启 DSH
```

验证（重启后）：

```powershell
# 路由是否挂上
curl http://127.0.0.1:<DSH端口>/dsh-cite/health
# 期望：{"ok":true,"plugin":"dsh-cite-style","version":"0.1.0",...}
```

## 配置（profile patch 覆盖）

```yaml
- id: dsh-cite-style
  name: dsh-cite-style
  config:
    enabled: true          # 关掉=不注入风格（路由仍可用）
    order: 0.2             # 提示段顺序（越小越靠前）
    maxBytes: 524288       # 预览文件上限（字节）
    contextLines: 12       # 高亮行上下各显示几行
    allowRoots: []         # 空=不限；填路径则只允许预览这些根目录下的文件
```

## 安全边界

- 路由**只读**，不执行任何程序、不写入；
- 只接受**本机 Host** + 同源请求（简易信任栅栏，降低 DNS rebinding 读取本地文件的风险）；
- 文件大小上限（默认 512 KB）+ 二进制文件拒渲染；
- 可用 `allowRoots` 把可预览范围收紧到指定目录。

## 已知限制

- 行号是否准确取决于**模型是否真的读过该文件**；本插件会在文件打不开时报警，但**无法判断行号是否指对内容**——这是「人看一眼预览页」的一步。
- 非 web composition（如纯 TUI）没有 HTTP 服务，`[n]` 会退化为纯文本标注，不影响写作纪律。
- 预览页不做 PDF/二进制解析；PDF 引用请写明页码。
