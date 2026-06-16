import { NextResponse } from 'next/server'
import https from 'node:https'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const OFFICIAL_BASE = 'https://spmb.jakarta.go.id'
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'

const ROUTE_CANDIDATES = [
  '1-sd-dom'
]

async function fetchJson(path: string) {
  return new Promise<unknown | null>((resolve) => {
    const request = https.request(
      `${OFFICIAL_BASE}${path}`,
      {
        method: 'GET',
        family: 4,
        timeout: 8000,
        headers: {
          accept: 'application/json',
          'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
          referer: `${OFFICIAL_BASE}/010101/sekilas`,
          'user-agent': USER_AGENT,
        },
      },
      response => {
        if (!response.statusCode || response.statusCode < 200 || response.statusCode >= 300) {
          response.resume()
          resolve(null)
          return
        }

        const contentType = String(response.headers['content-type'] || '')
        if (!contentType.includes('application/json')) {
          response.resume()
          resolve(null)
          return
        }

        const chunks: Buffer[] = []
        response.on('data', chunk => chunks.push(Buffer.from(chunk)))
        response.on('end', () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))
          } catch (error) {
            console.error(`Gagal parse ${path}:`, error)
            resolve(null)
          }
        })
      }
    )

    request.on('timeout', () => request.destroy(new Error(`Timeout ${path}`)))
    request.on('error', error => {
      console.error(`Gagal fetch ${path}:`, error)
      resolve(null)
    })
    request.end()
  })
}

export async function GET() {
  for (const routeKey of ROUTE_CANDIDATES) {
    const [sekolah, statistik] = await Promise.all([
      fetchJson(`/sekolah/${routeKey}.json`),
      fetchJson(`/statistik/${routeKey}.json`),
    ])

    if (sekolah && statistik) {
      return NextResponse.json({
        source: `${OFFICIAL_BASE}/010101/sekilas`,
        routeKey,
        sekolah,
        statistik,
      })
    }
  }

  return NextResponse.json(
    {
      error: 'Gagal mengambil data resmi SPMB Jakarta untuk /010101/sekilas',
      source: `${OFFICIAL_BASE}/010101/sekilas`,
    }
  )
}
