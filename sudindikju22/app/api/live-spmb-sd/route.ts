import { NextResponse } from 'next/server'
import { execFile } from 'node:child_process'
import https from 'node:https'
import { promisify } from 'node:util'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const OFFICIAL_BASES = [
  process.env.SPMB_OFFICIAL_BASE,
  'https://jakarta.spmb.id',
  'https://spmb.jakarta.go.id'
]
  .map(base => String(base || '').trim().replace(/\/$/, ''))
  .filter((base, index, list) => base && list.indexOf(base) === index)
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
const execFileAsync = promisify(execFile)

const ROUTE_CANDIDATES = [
  '1-sd-dom'
]

interface FetchAttempt {
  baseUrl: string
  path: string
  method: 'https' | 'curl'
  ok: boolean
  error?: string
}

async function fetchJsonViaHttps(baseUrl: string, path: string) {
  return new Promise<unknown>((resolve, reject) => {
    const request = https.request(
      `${baseUrl}${path}`,
      {
        method: 'GET',
        family: 4,
        timeout: 8000,
        headers: {
          accept: 'application/json',
          'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
          referer: `${baseUrl}/010101/sekilas`,
          'user-agent': USER_AGENT,
        },
      },
      response => {
        if (!response.statusCode || response.statusCode < 200 || response.statusCode >= 300) {
          response.resume()
          reject(new Error(`HTTP ${response.statusCode || 0}`))
          return
        }

        const contentType = String(response.headers['content-type'] || '')
        if (!contentType.includes('application/json')) {
          response.resume()
          reject(new Error(`Invalid content-type ${contentType}`))
          return
        }

        const chunks: Buffer[] = []
        response.on('data', chunk => chunks.push(Buffer.from(chunk)))
        response.on('end', () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))
          } catch (error) {
            reject(error)
          }
        })
      }
    )

    request.on('timeout', () => request.destroy(new Error(`Timeout ${path}`)))
    request.on('error', reject)
    request.end()
  })
}

async function fetchJsonViaCurl(baseUrl: string, path: string) {
  const { stdout } = await execFileAsync('curl', [
    '--fail',
    '--ipv4',
    '--silent',
    '--show-error',
    '--location',
    '--max-time',
    '12',
    '-H',
    'accept: application/json',
    '-H',
    'accept-language: id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
    '-H',
    `referer: ${baseUrl}/010101/sekilas`,
    '-H',
    `user-agent: ${USER_AGENT}`,
    `${baseUrl}${path}`
  ], { maxBuffer: 10 * 1024 * 1024 })

  return JSON.parse(stdout)
}

async function fetchJson(path: string, attempts: FetchAttempt[]) {
  for (const baseUrl of OFFICIAL_BASES) {
    try {
      const data = await fetchJsonViaHttps(baseUrl, path)
      attempts.push({ baseUrl, path, method: 'https', ok: true })
      return data
    } catch (error) {
      attempts.push({
        baseUrl,
        path,
        method: 'https',
        ok: false,
        error: error instanceof Error ? error.message : String(error)
      })
    }

    try {
      const data = await fetchJsonViaCurl(baseUrl, path)
      attempts.push({ baseUrl, path, method: 'curl', ok: true })
      return data
    } catch (error) {
      attempts.push({
        baseUrl,
        path,
        method: 'curl',
        ok: false,
        error: error instanceof Error ? error.message : String(error)
      })
    }
  }

  return null
}

export async function GET() {
  const attempts: FetchAttempt[] = []

  for (const routeKey of ROUTE_CANDIDATES) {
    const [sekolah, statistik] = await Promise.all([
      fetchJson(`/sekolah/${routeKey}.json`, attempts),
      fetchJson(`/statistik/${routeKey}.json`, attempts),
    ])

    if (sekolah && statistik) {
      return NextResponse.json({
        source: `${OFFICIAL_BASES[0]}/010101/sekilas`,
        routeKey,
        sekolah,
        statistik,
      })
    }
  }

  return NextResponse.json(
    {
      error: 'Gagal mengambil data resmi SPMB Jakarta untuk /010101/sekilas',
      source: `${OFFICIAL_BASES[0]}/010101/sekilas`,
      attempts,
    }
  )
}
