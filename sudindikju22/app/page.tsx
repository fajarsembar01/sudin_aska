// File: src/app/page.tsx
'use client'

import React, { useEffect, useState, useRef } from 'react'

export default function Page() {
  const [isLoaded, setIsLoaded] = useState(false)
  const askaButtonRef = useRef<HTMLAnchorElement>(null)

  useEffect(() => {
    setIsLoaded(true)
    // Delay focus slightly to ensure animations start/elements render
    const timer = setTimeout(() => {
      askaButtonRef.current?.focus()
    }, 800)
    return () => clearTimeout(timer)
  }, [])

  return (
    <main className="h-screen bg-gradient-to-br from-sky-50 via-white to-slate-100 overflow-hidden relative flex flex-col">
      {/* Animated Background Pattern */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-[400px] h-[400px] bg-gradient-to-br from-sky-200/30 to-blue-300/20 rounded-full blur-3xl animate-float" />
        <div className="absolute bottom-0 right-1/4 w-[350px] h-[350px] bg-gradient-to-br from-blue-200/25 to-indigo-300/15 rounded-full blur-3xl animate-float-delayed" />
        <div
          className="absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage: 'radial-gradient(circle, #0ea5e9 1px, transparent 1px)',
            backgroundSize: '20px 20px'
          }}
        />
      </div>

      {/* Navigation Bar */}
      <nav className={`w-full px-4 sm:px-6 py-3 flex items-center justify-between z-20 flex-shrink-0 transition-all duration-500 ${isLoaded ? 'opacity-100' : 'opacity-0'}`}>
        <div className="flex items-center gap-2 group cursor-pointer">
          <img
            src="/logo.png"
            alt="Logo Sudin Pendidikan"
            className="w-10 h-10 object-contain group-hover:scale-105 transition-transform duration-300"
          />
          <div className="hidden sm:block">
            <p className="text-sm font-bold text-sky-900">Sudin Pendidikan</p>
            <p className="text-xs text-slate-500">Jakarta Utara — Wilayah 2</p>
          </div>
        </div>
        <a
          href="https://admin.sudindikju2.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="relative inline-flex items-center gap-2 group/btn px-5 py-2.5 overflow-hidden rounded-full bg-gradient-to-r from-sky-600 to-blue-600 text-white font-bold text-xs shadow-lg shadow-sky-500/30 hover:shadow-sky-500/50 hover:scale-115 active:scale-95 transition-all duration-300 ring-1 ring-white/20"
        >
          <span className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover/btn:animate-[shine_1.5s_infinite]" />
          <span className="relative">Portal Kepegawaian</span>
          <svg className="relative w-3.5 h-3.5 group-hover/btn:translate-x-1 transition-transform duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 7l5 5m0 0l-5 5m5-5H6" />
          </svg>
        </a>
      </nav>

      {/* Main Content - Fits in viewport */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 min-h-0">
        <div className="w-full max-w-5xl">
          <div className="grid lg:grid-cols-2 gap-6 lg:gap-12 items-center">

            {/* Left Column - Compact Text */}
            <div className={`order-2 lg:order-1 text-center lg:text-left transition-all duration-700 ${isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-white/80 rounded-full mb-4 border border-sky-200/50 shadow-sm">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span className="text-xs font-medium text-slate-600">Dalam pengembangan</span>
              </div>

              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-slate-900 leading-tight mb-3">
                Suku Dinas{' '}
                <span className="bg-gradient-to-r from-sky-600 to-blue-600 bg-clip-text text-transparent">
                  Pendidikan
                </span>
                <br />
                <span className="text-slate-700 text-xl sm:text-2xl lg:text-3xl">Jakarta Utara — Wilayah 2</span>
              </h1>

              <p className="text-sm sm:text-base text-slate-600 mb-4 max-w-md mx-auto lg:mx-0">
                Portal layanan digital untuk pendidikan. Termasuk <strong className="text-sky-600">ASKA</strong> — Agen AI Sekolah Kita.
              </p>

              {/* Compact Feature Pills */}
              <div className="flex flex-wrap gap-1.5 justify-center lg:justify-start mb-4">
                {['Layanan Digital', 'Informasi Resmi', 'Dashboard', 'AI Assistant'].map((feature, i) => (
                  <span
                    key={feature}
                    className={`px-3 py-1 text-xs font-medium text-slate-600 bg-white/70 rounded-lg border border-slate-200/50 shadow-sm transition-all duration-300 ${isLoaded ? 'opacity-100' : 'opacity-0'}`}
                    style={{ transitionDelay: `${300 + i * 50}ms` }}
                  >
                    {feature}
                  </span>
                ))}
              </div>

              {/* Compact Progress */}
              <div className="bg-white/60 backdrop-blur-sm rounded-xl p-4 border border-white/50 shadow-lg max-w-sm mx-auto lg:mx-0">
                <p className="text-xs font-bold text-slate-700 mb-3 flex items-center gap-2">
                  <svg className="w-4 h-4 text-sky-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  Progress
                </p>
                <div className="space-y-2">
                  <ProgressCompact label="Desain" pct={80} isLoaded={isLoaded} delay={400} />
                  <ProgressCompact label="Frontend" pct={45} isLoaded={isLoaded} delay={500} />
                  <ProgressCompact label="ASKA" pct={75} isLoaded={isLoaded} delay={600} />
                </div>
              </div>
            </div>

            {/* Right Column - Video Card */}
            <div className={`order-1 lg:order-2 transition-all duration-700 ${isLoaded ? 'opacity-100 scale-100' : 'opacity-0 scale-95'}`}>
              <div className="relative max-w-sm mx-auto lg:max-w-none animate-float">
                {/* Stronger and larger blue aura */}
                <div className="absolute -top-10 -right-10 w-80 h-80 bg-sky-400/60 rounded-full blur-[80px] pointer-events-none" />
                <div className="absolute -bottom-12 -left-12 w-72 h-72 bg-blue-500/55 rounded-full blur-[80px] pointer-events-none" />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-indigo-400/40 rounded-full blur-[100px] pointer-events-none" />

                <div className="relative p-[3px] rounded-2xl bg-gradient-to-br from-sky-400 via-blue-500 to-indigo-500 shadow-2xl shadow-sky-500/50 group">
                  <div className="bg-white rounded-[14px] p-2">
                    <div className="relative aspect-[4/3] rounded-xl overflow-hidden">
                      <video
                        src="/aska.mp4"
                        autoPlay
                        loop
                        muted
                        playsInline
                        className="object-cover w-full h-full group-hover:scale-105 transition-transform duration-700"
                      />

                      <div className="absolute inset-0 bg-gradient-to-t from-slate-900/70 via-transparent to-transparent" />

                      <div className="absolute top-3 left-3">
                        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-white/90 rounded-full border border-white/50 shadow-md">
                          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                          <span className="text-[10px] font-bold text-slate-800">ASKA Online</span>
                        </div>
                      </div>

                      <div className="absolute bottom-0 left-0 right-0 p-4">
                        <div className="flex items-end justify-between">
                          <div>
                            <h3 className="text-lg font-extrabold text-white drop-shadow-lg">ASKA</h3>
                            <p className="text-xs text-white/80">Agen AI Sekolah Kita</p>
                          </div>
                          <a
                            ref={askaButtonRef}
                            href="http://aska.sudindikju2.com/"
                            className="relative inline-flex items-center gap-2 px-5 py-2.5 overflow-hidden rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 text-white font-bold text-xs shadow-lg shadow-emerald-500/30 hover:shadow-emerald-500/50 hover:scale-115 active:scale-95 focus:ring-2 focus:ring-emerald-400 focus:outline-none transition-all duration-300 group/aska ring-1 ring-white/20"
                          >
                            <span className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover/aska:animate-[shine_1.5s_infinite]" />
                            <span className="relative">Tanya ASKA!!</span>
                            <svg className="relative w-3.5 h-3.5 group-hover/aska:rotate-12 transition-transform duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                            </svg>
                          </a>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Compact Footer */}
      <footer className={`w-full px-4 py-3 border-t border-slate-200/50 bg-white/40 flex-shrink-0 transition-opacity duration-500 ${isLoaded ? 'opacity-100' : 'opacity-0'}`}>
        <div className="max-w-5xl mx-auto flex items-center justify-between text-xs text-slate-500">
          <span>© 2025 Sudin Pendidikan JU 2</span>
          <span className="hidden sm:inline">Dibangun dengan ❤️ untuk pendidikan</span>
        </div>
      </footer>

      <style jsx global>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-15px); }
        }
        @keyframes float-delayed {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-10px); }
        }
        .animate-float { animation: float 6s ease-in-out infinite; }
        .animate-float-delayed { animation: float-delayed 8s ease-in-out infinite; animation-delay: -2s; }
      `}</style>
    </main>
  )
}

function ProgressCompact({ label, pct, isLoaded, delay }: { label: string; pct: number; isLoaded: boolean; delay: number }) {
  return (
    <div className={`flex items-center gap-3 transition-all duration-500 ${isLoaded ? 'opacity-100' : 'opacity-0'}`} style={{ transitionDelay: `${delay}ms` }}>
      <span className="text-xs text-slate-600 w-16">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-1000"
          style={{
            width: isLoaded ? `${pct}%` : '0%',
            background: 'linear-gradient(90deg, #0ea5e9, #3b82f6)',
            transitionDelay: `${delay + 200}ms`
          }}
        />
      </div>
      <span className="text-xs font-semibold text-sky-600 w-8">{pct}%</span>
    </div>
  )
}
