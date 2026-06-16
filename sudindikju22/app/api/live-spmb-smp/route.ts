import { NextResponse } from 'next/server'
import { execFile } from 'node:child_process'
import https from 'node:https'
import { promisify } from 'node:util'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const OFFICIAL_BASE = 'https://spmb.jakarta.go.id'
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
const execFileAsync = promisify(execFile)

const ENDPOINTS = {
  smpSekolah: '/sekolah/1-smp-presaka.json',
  smpAkademik: '/statistik/1-smp-presaka.json',
  smpNonAkademik: '/statistik/1-smp-presnonaka.json',
  smaSekolah: '/sekolah/1-sma-presaka.json',
  smaAkademik: '/statistik/1-sma-presaka.json',
  smaMpmAkademik: '/statistik/1-sma-presnonaka.json',
}

interface FetchAttempt {
  path: string
  method: 'https' | 'curl'
  ok: boolean
  error?: string
}

async function fetchJsonViaHttps(path: string) {
  return new Promise<unknown>((resolve, reject) => {
    const request = https.request(
      `${OFFICIAL_BASE}${path}`,
      {
        method: 'GET',
        family: 4,
        timeout: 8000,
        headers: {
          accept: 'application/json',
          'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
          referer: `${OFFICIAL_BASE}/020201/hasil`,
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

async function fetchJsonViaCurl(path: string) {
  const { stdout } = await execFileAsync('curl', [
    '--fail',
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
    `referer: ${OFFICIAL_BASE}/020201/hasil`,
    '-H',
    `user-agent: ${USER_AGENT}`,
    `${OFFICIAL_BASE}${path}`
  ], { maxBuffer: 10 * 1024 * 1024 })

  return JSON.parse(stdout)
}

async function fetchJson(path: string, attempts: FetchAttempt[]) {
  try {
    const data = await fetchJsonViaHttps(path)
    attempts.push({ path, method: 'https', ok: true })
    return data
  } catch (error) {
    attempts.push({
      path,
      method: 'https',
      ok: false,
      error: error instanceof Error ? error.message : String(error)
    })
  }

  try {
    const data = await fetchJsonViaCurl(path)
    attempts.push({ path, method: 'curl', ok: true })
    return data
  } catch (error) {
    attempts.push({
      path,
      method: 'curl',
      ok: false,
      error: error instanceof Error ? error.message : String(error)
    })
    throw error
  }
}

export async function GET() {
  const attempts: FetchAttempt[] = []

  try {
    const [
      smpSekolah,
      smpAkademik,
      smpNonAkademik,
      smaSekolah,
      smaAkademik,
      smaMpmAkademik,
    ] = await Promise.all([
      fetchJson(ENDPOINTS.smpSekolah, attempts),
      fetchJson(ENDPOINTS.smpAkademik, attempts),
      fetchJson(ENDPOINTS.smpNonAkademik, attempts),
      fetchJson(ENDPOINTS.smaSekolah, attempts),
      fetchJson(ENDPOINTS.smaAkademik, attempts),
      fetchJson(ENDPOINTS.smaMpmAkademik, attempts),
    ])

    return NextResponse.json({
      source: {
        smpAkademik: `${OFFICIAL_BASE}/020201/hasil`,
        smpNonAkademik: `${OFFICIAL_BASE}/020301/sekilas`,
        smaAkademik: `${OFFICIAL_BASE}/030201/sekilas`,
        smaMpmAkademik: `${OFFICIAL_BASE}/030301/sekilas`,
      },
      smpSekolah,
      smpAkademik,
      smpNonAkademik,
      smaSekolah,
      smaAkademik,
      smaMpmAkademik,
    })
  } catch (error) {
    console.error('Gagal fetch data resmi SPMB SMP/SMA:', error)
    return NextResponse.json({
      error: 'Gagal mengambil data resmi SPMB Jakarta untuk SMP/SMA',
      attempts,
    })
  }
}
