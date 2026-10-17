/**
 * dsh-cite-style —— 科研论文式回答风格 + 可点击引用溯源（Host 半边）
 *
 * 做两件事：
 *   1. 通过 `systemPrompt.section()` 注入一段「回答风格契约」：先中文 IEEE 摘要式结论，
 *      再详细论述；引用用 [n] 标注；只引用真实读过的内容，禁止编造路径/行号/文献。
 *   2. 通过 `webServer.register()` 暴露只读预览路由 `/dsh-cite/source?path=&line=&end=`：
 *      模型把 [n] 写成指向该路由的 Markdown 链接，点击即可跳到源文（高亮指定行）；
 *      文件不存在时明确显示「可能为编造引用」，供人一眼核验。
 *
 * 依赖：只用宿主注入的服务（systemPrompt / webServer），不引入任何第三方包，
 * 因此在 TUI 等没有 web 服务的 composition 里也能安全加载（仅少掉路由）。
 *
 * @module dsh-cite-style
 */

import { promises as fsp } from 'node:fs'
import path from 'node:path'

/** 插件 id（与 package.json / bundle 行 id 一致）。 */
export const name = 'dsh-cite-style'

/** 只硬依赖 systemPrompt；webServer 在调用时探测（TUI 里可能没有）。 */
export const inject = ['systemPrompt']

/** 插件版本。 */
export const PLUGIN_VERSION = '0.1.0'

/** 路由前缀。 */
export const ROUTE_PREFIX = '/dsh-cite'

/** 提示段名（与其它插件区分开）。 */
const SECTION_NAME = 'cite-style:paper'

/** 默认配置。 */
const DEFAULT_CONFIG = {
  enabled: true,
  order: 0.2,
  /** 只读预览允许的最大文件字节数。 */
  maxBytes: 512 * 1024,
  /** 高亮行上下各显示多少行。 */
  contextLines: 12,
  /** 为空 = 允许任意可读文本文件；非空 = 只允许这些根目录下的文件（防越权读取）。 */
  allowRoots: [],
}

/** 回答风格契约：由 style.policy.yaml 经 tools/gen_style.py 生成（勿手改）。 */
import { STYLE_PROMPT, DENY_PATTERNS } from './style.prompt.mjs'

/** 归一化配置：坏值回落到默认，不因配置问题让插件加载失败。 */
function normalizeConfig(raw) {
  const c = raw && typeof raw === 'object' ? raw : {}
  const num = (v, d) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : d)
  return {
    enabled: c.enabled !== false,
    order: num(c.order, DEFAULT_CONFIG.order),
    maxBytes: Math.max(4096, Math.min(num(c.maxBytes, DEFAULT_CONFIG.maxBytes), 16 * 1024 * 1024)),
    contextLines: Math.max(0, Math.min(num(c.contextLines, DEFAULT_CONFIG.contextLines), 200)),
    allowRoots: Array.isArray(c.allowRoots) ? c.allowRoots.filter((x) => typeof x === 'string' && x) : [],
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function hostIsLocal(hostHeader) {
  const h = String(hostHeader || '').toLowerCase().replace(/:\d+$/, '').replace(/^\[|\]$/g, '')
  return h === 'localhost' || h === '127.0.0.1' || h === '::1'
}

/** 页面外壳（自包含，无外链资源）。 */
function page(title, bodyHtml) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
:root{color-scheme:light dark}
body{margin:0;padding:16px 18px;font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,"Cascadia Code",monospace;
     background:#0f1115;color:#d7dae0}
@media (prefers-color-scheme:light){body{background:#fbfbfc;color:#20242b}}
.hd{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;margin-bottom:10px}
.path{font-weight:600;word-break:break-all}
.meta{opacity:.62;font-size:12px}
.note{margin:0 0 12px;padding:8px 10px;border-left:3px solid #4a8cff;background:rgba(74,140,255,.08);font-size:12.5px}
.warn{margin:0 0 12px;padding:10px 12px;border-left:3px solid #ff6b6b;background:rgba(255,107,107,.1)}
pre{margin:0;overflow:auto;counter-reset:ln}
.row{display:flex;gap:10px;white-space:pre}
.ln{flex:0 0 auto;min-width:4.2em;text-align:right;opacity:.4;user-select:none}
.tx{flex:1 1 auto;white-space:pre-wrap;word-break:break-word}
.hit{background:rgba(255,196,0,.18);outline:1px solid rgba(255,196,0,.35);border-radius:3px}
.hit .ln{opacity:.85;color:#ffc400}
a{color:#6ea8ff}
</style></head><body>${bodyHtml}</body></html>`
}

/** 渲染「找不到文件」页：这是核验"是否编造引用"的关键反馈。 */
function missingPage(target, reason) {
  return page('引用来源不存在', `
<div class="hd"><span class="path">⚠️ 引用的来源不可用</span></div>
<p class="warn"><b>目标：</b>${escapeHtml(target)}<br><b>原因：</b>${escapeHtml(reason)}</p>
<p class="note">这条 <code>[n]</code> 指向的文件/路径无法读取，<b>极可能是编造的引用</b>（或文件已被移动/删除）。
请回到对话要求模型核实来源，或让模型先真正读取该文件再引用。</p>`)
}

/**
 * 处理 `/dsh-cite/source?path=&line=&end=&title=`。
 * 只读、有大小上限、可选根目录白名单；绝不执行任何程序。
 */
async function handleSource(req, res, cfg) {
  const send = (code, html) => {
    res.statusCode = code
    res.setHeader('Content-Type', 'text/html; charset=utf-8')
    res.setHeader('Cache-Control', 'no-store')
    res.setHeader('X-Content-Type-Options', 'nosniff')
    res.end(html)
  }

  // 简易信任栅栏：只接受本机 Host，且拒绝跨站发起的请求（防 DNS rebinding 读取本地文件）。
  const site = String(req.headers['sec-fetch-site'] || '')
  if (!hostIsLocal(req.headers.host) || (site && site !== 'same-origin' && site !== 'none')) {
    send(403, page('拒绝访问', '<p class="warn">只允许本机同源访问。</p>'))
    return
  }

  let url
  try {
    url = new URL(req.url, 'http://localhost')
  } catch {
    send(400, page('参数错误', '<p class="warn">URL 解析失败。</p>'))
    return
  }

  const rawPath = url.searchParams.get('path') || ''
  if (!rawPath.trim()) {
    send(400, page('参数错误', '<p class="warn">缺少 <code>path</code> 参数。</p>'))
    return
  }

  // 路径解析：绝对路径直接用；相对路径相对进程 cwd。
  const abs = path.isAbsolute(rawPath) ? path.normalize(rawPath) : path.resolve(process.cwd(), rawPath)

  // 可选白名单
  if (cfg.allowRoots.length) {
    const ok = cfg.allowRoots.some((root) => {
      const r = path.resolve(root)
      return abs === r || abs.startsWith(r.endsWith(path.sep) ? r : r + path.sep)
    })
    if (!ok) {
      send(403, missingPage(abs, '路径不在 allowRoots 白名单内'))
      return
    }
  }

  // 敏感文件名黑名单（来自 style.policy.yaml 的 privacy.sensitive_name_patterns）
  const low = abs.toLowerCase()
  const denied = DENY_PATTERNS.find((p) => low.includes(String(p).toLowerCase()))
  if (denied) {
    send(403, missingPage(abs, `命中敏感文件名黑名单（${denied}），拒绝预览`))
    return
  }

  let stat
  try {
    stat = await fsp.stat(abs)
  } catch {
    send(404, missingPage(abs, '文件不存在'))
    return
  }
  if (!stat.isFile()) {
    send(400, missingPage(abs, '目标不是文件（可能是目录）'))
    return
  }
  if (stat.size > cfg.maxBytes) {
    send(413, missingPage(abs, `文件过大（${stat.size} 字节 > 上限 ${cfg.maxBytes}）`))
    return
  }

  let buf
  try {
    buf = await fsp.readFile(abs)
  } catch (e) {
    send(500, missingPage(abs, '读取失败：' + String(e && e.message ? e.message : e)))
    return
  }
  if (buf.includes(0)) {
    send(415, page('二进制文件', `<div class="hd"><span class="path">${escapeHtml(abs)}</span></div>
<p class="note">这是二进制文件，无法以文本预览（${stat.size} 字节）。引用位于其中的内容请说明页码/图号。</p>`))
    return
  }

  const text = buf.toString('utf8').replace(/^\uFEFF/, '')
  const lines = text.split(/\r?\n/)
  const total = lines.length

  const clamp = (v, d) => {
    const n = Number.parseInt(v ?? '', 10)
    return Number.isFinite(n) && n > 0 ? n : d
  }
  const start = clamp(url.searchParams.get('line'), 1)
  const endRaw = clamp(url.searchParams.get('end'), start)
  const end = Math.max(start, Math.min(endRaw, total))
  const from = Math.max(1, start - cfg.contextLines)
  const to = Math.min(total, end + cfg.contextLines)

  const rows = []
  for (let i = from; i <= to; i += 1) {
    const hit = i >= start && i <= end
    rows.push(
      `<div class="row${hit ? ' hit' : ''}"><span class="ln">${i}</span><span class="tx">${escapeHtml(lines[i - 1] ?? '')}</span></div>`
    )
  }

  const rangeLabel = end > start ? `${start}–${end}` : String(start)
  const title = url.searchParams.get('title') || path.basename(abs)
  send(200, page(title, `
<div class="hd">
  <span class="path">${escapeHtml(abs)}</span>
  <span class="meta">第 ${rangeLabel} 行 / 共 ${total} 行 · 文件 ${stat.size} 字节</span>
</div>
<p class="note">只读预览：黄色高亮为引用位置；行号可直接写进 <code>[n]</code> 链接的 <code>line</code>/<code>end</code> 参数。</p>
<pre>${rows.join('\n')}</pre>`))
}

/** 健康检查：用于安装后验证路由确实挂上了。 */
function handleHealth(res) {
  res.statusCode = 200
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(JSON.stringify({ ok: true, plugin: name, version: PLUGIN_VERSION, routes: [`${ROUTE_PREFIX}/source`, `${ROUTE_PREFIX}/health`] }))
}

/**
 * @param {import('@deepseek-ai/cordis').Context} ctx
 * @param {unknown} config
 */
export function apply(ctx, config) {
  const cfg = () => normalizeConfig(config)

  // ── 1) 提示段：回答风格契约 ────────────────────────────────────────────────
  let disposeSection = null
  const registerSection = () => {
    if (disposeSection) {
      disposeSection()
      disposeSection = null
    }
    const c = cfg()
    if (!c.enabled) return
    try {
      disposeSection = ctx.systemPrompt.section({
        name: SECTION_NAME,
        order: c.order,
        text: STYLE_PROMPT,
        interpolate: false,
      })
    } catch (error) {
      ctx.logger?.warn?.(`[${name}] 提示段注册失败：${String(error?.message ?? error)}`)
    }
  }
  ctx.effect(() => {
    registerSection()
    return () => {
      if (disposeSection) {
        disposeSection()
        disposeSection = null
      }
    }
  }, `${name}.section()`)

  // ── 2) 只读预览路由（插件可能在 web 服务发布之前挂载 → 需要重试等待） ───────
  ctx.effect(() => {
    let disposed = false
    let timer = null
    const disposers = []

    const handler = (req, res) => {
      const url = String(req.url || '')
      if (url.startsWith(`${ROUTE_PREFIX}/health`)) return handleHealth(res)
      if (!url.startsWith(`${ROUTE_PREFIX}/source`)) {
        res.statusCode = 404
        res.setHeader('Content-Type', 'text/plain; charset=utf-8')
        res.end('not found')
        return
      }
      handleSource(req, res, cfg()).catch((error) => {
        try {
          res.statusCode = 500
          res.setHeader('Content-Type', 'text/html; charset=utf-8')
          res.end(page('内部错误', `<p class="warn">${escapeHtml(String(error?.message ?? error))}</p>`))
        } catch {
          /* 已结束 */
        }
      })
    }

    const getWeb = () => {
      try {
        return typeof ctx.get === 'function' ? ctx.get('webServer') : null
      } catch {
        return null
      }
    }

    const registerOn = (web) => {
      try {
        disposers.push(web.register({ kind: 'prefix', path: ROUTE_PREFIX, handler }))
        ctx.logger?.info?.(`[${name}] 引用预览路由已就绪（prefix）：${ROUTE_PREFIX}/source`)
        return true
      } catch (error) {
        ctx.logger?.warn?.(`[${name}] prefix 注册失败，改用 exact：${String(error?.message ?? error)}`)
      }
      let ok = false
      for (const suffix of ['/health', '/source']) {
        try {
          disposers.push(web.register({ kind: 'exact', path: `${ROUTE_PREFIX}${suffix}`, handler }))
          ok = true
        } catch (error) {
          ctx.logger?.warn?.(`[${name}] exact 注册失败 ${suffix}：${String(error?.message ?? error)}`)
        }
      }
      if (ok) ctx.logger?.info?.(`[${name}] 引用预览路由已就绪（exact）：${ROUTE_PREFIX}/source`)
      return ok
    }

    const attempt = (n) => {
      if (disposed) return
      const web = getWeb()
      if (!web || typeof web.register !== 'function') {
        if (n === 0) ctx.logger?.info?.(`[${name}] webServer 尚未发布，开始重试（最多 10s）`)
        if (n < 40) timer = setTimeout(() => attempt(n + 1), 250)
        else ctx.logger?.warn?.(`[${name}] 等待 webServer 超时，未注册引用预览路由（非 web composition 属正常）`)
        return
      }
      registerOn(web)
    }
    attempt(0)

    return () => {
      disposed = true
      if (timer) clearTimeout(timer)
      for (const dispose of disposers) {
        try {
          dispose()
        } catch {
          /* 忽略 */
        }
      }
    }
  }, `${name}.routes()`)
}
