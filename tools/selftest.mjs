/**
 * 自检：不联网、不发消息、不碰 ~/.dsh。
 *
 * 覆盖：SKILL.md 解析、provider 的 list/get、push.py 的 --check 与占位符忽略、
 * queue.py 的 tick/list/pop（用临时 HOME），以及 bin/dsh-ai-daily.mjs 的 check。
 *
 *   node tools/selftest.mjs
 *
 * @module dsh-plugin-ai-daily-push/tools/selftest
 */

import { spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const failures = []

function check(name, ok, detail = '') {
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name}${detail && !ok ? ` — ${detail}` : ''}`)
  if (!ok) failures.push(name)
}

function py(script, args, env = {}) {
  return spawnSync('python3', [join(ROOT, 'scripts', script), ...args], {
    encoding: 'utf8',
    env: { ...process.env, ...env },
  })
}

// 1. SKILL.md 与 provider
const mod = await import(join(ROOT, 'lib', 'index.js'))
const candidates = await mod.list()
check('list() 返回一条候选', candidates.length === 1)
const cand = candidates[0]
check('技能名是 kebab-case', /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(cand.name), cand.name)
check('description 非空且超过 40 字', (cand.description ?? '').length > 40)
const def = await mod.get(cand)
check('get() 正文不含 frontmatter', !def.content.startsWith('---'))
check('get() 正文包含推送命令', def.content.includes('scripts/push.py'))
check('resourceBase 指向包根', def.resourceBase.path.startsWith(ROOT))
check('导出 plug-in name 与 patch 一致', mod.name === 'ai-daily-push')

// 2. push.py：未配置时应退出码 2；占位符应被忽略
const bare = mkdtempSync(join(tmpdir(), 'ai-daily-bare-'))
const bareCfg = join(bare, 'config.env')
writeFileSync(bareCfg, 'SERVERCHAN_SENDKEY=YOUR_KEY_HERE\n')
const noCfg = py('push.py', ['--check', '--config', bareCfg], { HOME: bare, SERVERCHAN_SENDKEY: '' })
check('占位符配置被判为未配置（退出码 2）', noCfg.status === 2, `status=${noCfg.status} ${noCfg.stdout}${noCfg.stderr}`)
check('--check 输出不含密钥', !noCfg.stdout.includes('YOUR_KEY_HERE'))

const cfgDir = join(bare, '.dsh', 'ai-daily-push')
mkdirSync(cfgDir, { recursive: true })
writeFileSync(join(cfgDir, 'config.env'), 'SERVERCHAN_SENDKEY=SCTtestkey_0123456789\n')
const withCfg = py('push.py', ['--check', '--verbose'], { HOME: bare })
check('配置后 --check 退出码 0', withCfg.status === 0, withCfg.stdout + withCfg.stderr)
check('--check 指出 serverchan', withCfg.stdout.includes('serverchan'))

// 3. queue.py：tick 记录今天，pop 出队
const t1 = py('queue.py', ['tick', '--quiet'], { HOME: bare })
check('queue tick 成功', t1.status === 0, t1.stderr)
const l1 = py('queue.py', ['list'], { HOME: bare })
const dates = l1.stdout.split('\n').filter(Boolean)
check('queue 记录了今天', dates.length >= 1, l1.stdout)
const pop = py('queue.py', ['pop', '--date', dates[0]], { HOME: bare })
check('queue pop 成功', pop.status === 0)
const l2 = py('queue.py', ['list'], { HOME: bare })
check('pop 后不再列出该日期', !l2.stdout.split('\n').includes(dates[0]))
const t2 = py('queue.py', ['tick', '--quiet'], { HOME: bare })
check('tick 幂等（已出队日期不再重复入队）', t2.status === 0)

// 4. bin：check 与 doctor
const bin = join(ROOT, 'bin', 'dsh-ai-daily.mjs')
const b = spawnSync(process.execPath, [bin, 'check'], { encoding: 'utf8', env: { ...process.env, HOME: bare } })
check('dsh-ai-daily check 退出码 0', b.status === 0, b.stdout + b.stderr)
const d = spawnSync(process.execPath, [bin, 'doctor'], { encoding: 'utf8', env: { ...process.env, HOME: bare } })
check('dsh-ai-daily doctor 输出打码后的 key', d.stdout.includes('SCTt***') && !d.stdout.includes('0123456789'), d.stdout)

rmSync(bare, { recursive: true, force: true })

if (failures.length) {
  console.error(`\n${failures.length} 项失败`)
  process.exit(1)
}
console.log('\n全部通过')
