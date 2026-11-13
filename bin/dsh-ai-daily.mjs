#!/usr/bin/env node
/**
 * `dsh-ai-daily` —— 无需打开桌面端也能跑的那一半。
 *
 * 桌面端的定时任务负责「写简报」，但它只在宿主进程运行时触发。本文件给 cron /
 * launchd / Windows 任务计划程序一个入口：
 *
 *   dsh-ai-daily tick          记录今天（及最近 7 天内漏掉的）还没生成的日子，写日志
 *   dsh-ai-daily tick --print  同上，顺带把新增日期打印到 stdout（给 tail 用）
 *   dsh-ai-daily list          列出待生成日期
 *   dsh-ai-daily check         检查微信通道是否已配置（退出码同 push.py --check）
 *   dsh-ai-daily push --title T --file F   直接调用 scripts/push.py
 *   dsh-ai-daily doctor        打印路径、Python 版本、通道与最近日志（密钥已打码）
 *
 * 只 import `node:` 内置模块，零依赖。
 *
 * @module dsh-plugin-ai-daily-push/bin
 */

import { spawnSync } from 'node:child_process'
import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const PUSH_PY = join(ROOT, 'scripts', 'push.py')
const QUEUE_PY = join(ROOT, 'scripts', 'queue.py')
const HOME = join(homedir(), '.dsh', 'ai-daily-push')
const LOG_DIR = join(HOME, 'logs')
const LOG_FILE = join(LOG_DIR, 'tick.log')
const CONFIG = join(HOME, 'config.env')

/** 依次尝试的 Python 解释器，可用 AI_DAILY_PYTHON 覆盖。 */
const PYTHONS = [process.env.AI_DAILY_PYTHON, 'python3', 'python'].filter(Boolean)

function stamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function log(line) {
  mkdirSync(LOG_DIR, { recursive: true })
  appendFileSync(LOG_FILE, `[${stamp()}] ${line}\n`, 'utf8')
}

/** 跑一个 Python 脚本；找不到解释器时返回 { status: null, error }。 */
function runPy(script, args) {
  const errors = []
  for (const bin of PYTHONS) {
    const res = spawnSync(bin, [script, ...args], { encoding: 'utf8' })
    if (res.error && res.error.code === 'ENOENT') {
      errors.push(`${bin}: not found`)
      continue
    }
    if (res.error) {
      errors.push(`${bin}: ${res.error.message}`)
      continue
    }
    return res
  }
  return { status: null, stdout: '', stderr: `没有可用的 Python（尝试过 ${errors.join(', ')}）` }
}

/** 把 config.env 里的密钥替换掉，日志里只留文件本身。 */
function redactConfig() {
  if (!existsSync(CONFIG)) return '（尚未创建）'
  const text = readFileSync(CONFIG, 'utf8')
  return text
    .split('\n')
    .map((line) => {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.+)$/)
      if (!m) return line
      const value = m[2].trim().replace(/^["']|["']$/g, '')
      return `${m[1]}=${value.length > 4 ? value.slice(0, 4) + '***' : '***'}`
    })
    .join('\n')
}

function tick(opts) {
  const before = runPy(QUEUE_PY, ['list'])
  const res = runPy(QUEUE_PY, ['tick', '--quiet'])
  if (res.status !== 0) {
    log(`tick 失败: ${res.stderr.trim() || `exit ${res.status}`}`)
    console.error(res.stderr.trim() || `queue.py tick 退出码 ${res.status}`)
    return res.status ?? 1
  }
  const after = runPy(QUEUE_PY, ['list'])
  const queued = new Set(before.stdout.split('\n').filter(Boolean))
  const added = after.stdout.split('\n').filter((d) => d && !queued.has(d))
  const check = runPy(PUSH_PY, ['--check'])
  const channel = check.stdout.trim()
  log(`tick ok；待生成: ${after.stdout.split('\n').filter(Boolean).join(', ') || '无'}；新增: ${added.join(', ') || '无'}；${channel}`)
  if (added.length) {
    console.log(`待生成: ${added.join(', ')}`)
    if (opts.print) console.log(`提示词：补写 ${added.join(', ')} 这几天的 AI 日报，写完后逐条执行 python3 ${QUEUE_PY} pop --date <日期>`)
  } else {
    console.log('待生成: 无（最近几天都已有简报）')
  }
  if (check.status !== 0) console.log('微信推送通道尚未配置：请按 README 填写 ~/.dsh/ai-daily-push/config.env')
  return 0
}

function list() {
  const res = runPy(QUEUE_PY, ['list'])
  process.stdout.write(res.stdout || '')
  return res.status ?? 1
}

function check() {
  const res = runPy(PUSH_PY, ['--check', '--verbose'])
  process.stdout.write(res.stdout)
  process.stderr.write(res.stderr)
  return res.status ?? 1
}

function push(args) {
  const res = runPy(PUSH_PY, args)
  process.stdout.write(res.stdout)
  process.stderr.write(res.stderr)
  log(`push ${res.status === 0 ? 'ok' : 'failed'}：${res.stdout.trim().slice(0, 200) || res.stderr.trim().slice(0, 200)}`)
  return res.status ?? 1
}

function doctor() {
  const py = runPy('-c', ['import sys;print(sys.version.split()[0])'])
  const days = existsSync(join(HOME, 'digests'))
    ? readdirSync(join(HOME, 'digests')).filter((f) => /^ai-\d{4}-\d{2}-\d{2}\.md$/.test(f)).sort()
    : []
  const logs = existsSync(LOG_FILE) ? readFileSync(LOG_FILE, 'utf8').trim().split('\n').slice(-5) : []
  console.log(`包目录      ${ROOT}`)
  console.log(`数据目录    ${HOME}`)
  console.log(`Python      ${py.status === 0 ? py.stdout.trim() : pf(py.stderr)}`)
  console.log(`简报数量    ${days.length}（最新: ${days.at(-1) ?? '无'}）`)
  console.log(`通道        ${runPy(PUSH_PY, ['--check']).stdout.trim()}`)
  console.log(`config.env  ${redactConfig().split('\n').slice(0, 12).join('\n            ')}`)
  console.log(`最近日志    ${logs.length ? '\n            ' + logs.join('\n            ') : '（无）'}`)
  return 0
}

function pf(s) {
  return (s ?? '').trim() || '不可用'
}

function usage() {
  console.log(`用法: dsh-ai-daily <命令>

  tick [--print]      记录今天（及最近 7 天漏掉的）未生成日期，并检查推送通道
  list                列出待生成日期
  check               检查微信推送通道是否已配置
  push [push.py 参数] 直接推送，如: dsh-ai-daily push --title "AI 日报" --file a.md
  doctor              打印路径、Python 版本、通道、最近日志（密钥已打码）

环境变量:
  AI_DAILY_PYTHON     Python 解释器路径（默认依次试 python3、python）`)
}

function main(argv) {
  const [cmd, ...rest] = argv
  switch (cmd) {
    case 'tick':
      return tick({ print: rest.includes('--print') })
    case 'list':
      return list()
    case 'check':
      return check()
    case 'push':
      return push(rest)
    case 'doctor':
      return doctor()
    case undefined:
    case '-h':
    case '--help':
      usage()
      return 0
    default:
      console.error(`未知命令: ${cmd}`)
      usage()
      return 2
  }
}

process.exitCode = main(process.argv.slice(2))
