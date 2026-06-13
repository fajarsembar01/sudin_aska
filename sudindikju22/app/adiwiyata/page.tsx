'use client'

import React, { useEffect, useState, useRef, useCallback } from 'react'

interface Post {
  id: number;
  school_id: number;
  school_name: string;
  school_logo_url?: string | null;
  category: string;
  media_type: string;
  media_urls: string[] | null;
  media_path: string | null;
  description: string;
  created_at: string;
}

interface Photo {
  id: number;
  url: string;
  school_id?: number;
  school_name: string;
  school_logo_url?: string | null;
  category?: string;
  description?: string;
  created_at?: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  'pengelolaan-sampah': 'Pengelolaan Sampah',
  'konservasi-energi': 'Konservasi Energi',
  'konservasi-air': 'Konservasi Air',
  'kebersihan-sanitasi-drainase': 'Kebersihan & Sanitasi',
  'kompos': 'Kompos',
  'tanaman': 'Tanaman',
}

const CATEGORY_ICONS: Record<string, string> = {
  'pengelolaan-sampah': '🗑️',
  'konservasi-energi': '⚡',
  'konservasi-air': '💧',
  'kebersihan-sanitasi-drainase': '✨',
  'kompos': '♻️',
  'tanaman': '🌿',
}

const CATEGORY_COLORS: Record<string, string> = {
  'pengelolaan-sampah': 'from-amber-400 to-orange-500',
  'konservasi-energi': 'from-yellow-400 to-amber-500',
  'konservasi-air': 'from-sky-400 to-blue-500',
  'kebersihan-sanitasi-drainase': 'from-violet-400 to-purple-500',
  'kompos': 'from-emerald-400 to-teal-500',
  'tanaman': 'from-green-400 to-emerald-600',
}

const SchoolLogoAvatar = ({
  name,
  logoUrl,
  colorClass,
  className = 'w-12 h-12 rounded-2xl text-lg',
}: {
  name: string;
  logoUrl?: string | null;
  colorClass: string;
  className?: string;
}) => {
  const initial = (name || 'S').charAt(0).toUpperCase()

  return (
    <div className={`relative ${className} overflow-hidden flex-shrink-0 bg-white border border-white/70 shadow-lg`}>
      {logoUrl && (
        <img
          src={logoUrl}
          alt={`Logo ${name || 'sekolah'}`}
          className="absolute inset-0 w-full h-full object-cover"
          onError={e => {
            e.currentTarget.style.display = 'none'
            const fallback = e.currentTarget.nextElementSibling as HTMLElement | null
            fallback?.classList.remove('hidden')
            fallback?.classList.add('flex')
          }}
        />
      )}
      <span className={`absolute inset-0 ${logoUrl ? 'hidden' : 'flex'} items-center justify-center bg-gradient-to-br ${colorClass} text-white font-black`}>
        {initial}
      </span>
    </div>
  )
}

// ─── LIKES & DISLIKES COMPONENT ───
const PostActions = ({ postId }: { postId: number }) => {
  const [likes, setLikes] = useState(0)
  const [dislikes, setDislikes] = useState(0)
  const [userAction, setUserAction] = useState<string | null>(null) // 'like', 'dislike', or null

  const getFingerprint = () => {
    let fp = localStorage.getItem('fp_adiwiyata')
    if (!fp) {
      fp = Math.random().toString(36).substring(2) + Date.now().toString(36)
      localStorage.setItem('fp_adiwiyata', fp)
    }
    return fp
  }

  useEffect(() => {
    const fp = getFingerprint()
    fetch(`http://127.0.0.1:5002/portal/api/public/adiwiyata/posts/${postId}/likes?fp=${fp}`)
      .then(r => r.json())
      .then(d => { 
        setLikes(d.likes || 0)
        setDislikes(d.dislikes || 0)
        setUserAction(d.user_action || null)
      })
      .catch(console.error)
  }, [postId])

  const handleAction = (actionType: 'like' | 'dislike') => {
    // Optimistic UI update
    const previousAction = userAction;
    
    // Calculate new state
    if (previousAction === actionType) {
      // Removing the action
      setUserAction(null);
      if (actionType === 'like') setLikes(Math.max(0, likes - 1));
      if (actionType === 'dislike') setDislikes(Math.max(0, dislikes - 1));
    } else {
      // Switching to or adding new action
      setUserAction(actionType);
      
      if (actionType === 'like') {
        setLikes(likes + 1);
        if (previousAction === 'dislike') setDislikes(Math.max(0, dislikes - 1));
      } else {
        setDislikes(dislikes + 1);
        if (previousAction === 'like') setLikes(Math.max(0, likes - 1));
      }
    }

    // API call
    fetch(`http://127.0.0.1:5002/portal/api/public/adiwiyata/posts/${postId}/likes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fingerprint: getFingerprint(), action: actionType })
    })
      .then(r => r.json())
      .then(d => { 
        if (d.likes !== undefined) setLikes(d.likes)
        if (d.dislikes !== undefined) setDislikes(d.dislikes)
        if (d.action !== undefined) setUserAction(d.action === 'removed' ? null : d.action)
      })
      .catch(console.error)
  }

  return (
    <div className="border-t border-slate-100 bg-slate-50/50">
      <div className="flex items-center gap-1 px-3 py-2 border-b border-slate-100">
        <button 
          onClick={() => handleAction('like')}
          className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-xl text-sm font-bold transition-all ${userAction === 'like' ? 'text-emerald-600 bg-emerald-50' : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'}`}
        >
          <svg className={`w-5 h-5 ${userAction === 'like' ? 'fill-current' : 'fill-none'}`} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" /></svg>
          Suka {likes > 0 && <span className="ml-1 bg-slate-200/50 px-2 py-0.5 rounded-full text-xs">{likes}</span>}
        </button>
        <button 
          onClick={() => handleAction('dislike')}
          className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-xl text-sm font-bold transition-all ${userAction === 'dislike' ? 'text-red-600 bg-red-50' : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'}`}
        >
          <svg className={`w-5 h-5 ${userAction === 'dislike' ? 'fill-current' : 'fill-none'} transform rotate-180`} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" /></svg>
          Tidak Suka {dislikes > 0 && <span className="ml-1 bg-slate-200/50 px-2 py-0.5 rounded-full text-xs">{dislikes}</span>}
        </button>
      </div>
    </div>
  )
}

export default function AdiwiyataPage() {
  const [posts, setPosts] = useState<Post[]>([])
  const [photos, setPhotos] = useState<Photo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [lightboxIndex, setLightboxIndex] = useState(-1)
  const [lightboxUrls, setLightboxUrls] = useState<string[]>([])
  const [activePost, setActivePost] = useState<Post | null>(null)
  const [isLoaded, setIsLoaded] = useState(false)
  const [visiblePosts, setVisiblePosts] = useState<Set<number>>(new Set())
  const postRefs = useRef<Map<number, HTMLDivElement>>(new Map())
  const observerRef = useRef<IntersectionObserver | null>(null)

  useEffect(() => {
    setTimeout(() => setIsLoaded(true), 100)

    fetch('http://127.0.0.1:5002/portal/api/public/adiwiyata/random-photos?limit=30')
      .then(res => res.json())
      .then(data => { if (data?.photos) setPhotos(data.photos) })
      .catch(console.error)

    fetchPosts(1)
  }, [])

  useEffect(() => {
    observerRef.current = new IntersectionObserver(
      (entries) => {
        entries.forEach(e => {
          if (e.isIntersecting) {
            const id = Number((e.target as HTMLElement).dataset.postid)
            setVisiblePosts(prev => new Set([...prev, id]))
          }
        })
      },
      { threshold: 0.1, rootMargin: '0px 0px -50px 0px' }
    )
    return () => observerRef.current?.disconnect()
  }, [])

  const registerPostRef = useCallback((el: HTMLDivElement | null, id: number) => {
    if (el && observerRef.current) {
      postRefs.current.set(id, el)
      observerRef.current.observe(el)
    }
  }, [])

  const fetchPosts = (pageNumber: number) => {
    setIsLoading(true)
    fetch(`http://127.0.0.1:5002/portal/api/public/adiwiyata/posts?page=${pageNumber}&per_page=10`)
      .then(res => res.json())
      .then(data => {
        if (data?.posts) {
          setPosts(prev => pageNumber === 1 ? data.posts : [...prev, ...data.posts])
          setHasMore(data.has_more)
        }
      })
      .catch(console.error)
      .finally(() => setIsLoading(false))
  }

  const loadMore = () => {
    if (!isLoading && hasMore) {
      const next = page + 1
      setPage(next)
      fetchPosts(next)
    }
  }

  const openLightbox = (urls: string[], idx = 0, post: Post | null = null) => {
    setLightboxUrls(urls)
    setLightboxIndex(idx)
    setActivePost(post)
    document.body.style.overflow = 'hidden'
  }

  const openPhotoLightbox = (photo: Photo) => {
    const category = photo.category || 'pengelolaan-sampah'
    const post: Post | null = photo.school_id ? {
      id: photo.id,
      school_id: photo.school_id,
      school_name: photo.school_name || 'Sekolah',
      school_logo_url: photo.school_logo_url || null,
      category,
      media_type: 'image',
      media_urls: [photo.url],
      media_path: photo.url,
      description: photo.description || '',
      created_at: photo.created_at || new Date().toISOString(),
    } : null

    openLightbox([photo.url], 0, post)
  }

  const closeLightbox = () => {
    setLightboxIndex(-1)
    setActivePost(null)
    document.body.style.overflow = ''
  }

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  }

  const formatTime = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) + ' WIB'
  }

  const getPlatformInfo = (url: string) => {
    if (!url) return { type: 'unknown', id: null };
    const ytMatch = url.match(/(?:youtube\.com\/(?:[^/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?/\s]{11})/i);
    if (ytMatch) return { type: 'youtube', id: ytMatch[1] };
    const ttMatch = url.match(/(?:tiktok\.com\/.*\/video\/|tiktok\.com\/v\/|vt\.tiktok\.com\/)([\w\d]+)/i);
    if (ttMatch) return { type: 'tiktok', id: ttMatch[1] };
    const igMatch = url.match(/instagram\.com\/(?:p|reel|tv)\/([A-Za-z0-9_-]+)/i);
    if (igMatch) return { type: 'instagram', id: igMatch[1] };
    const gdMatch = url.match(/drive\.google\.com\/(?:file\/d\/|open\?id=)([\w-]+)/i);
    if (gdMatch) return { type: 'gdrive', id: gdMatch[1] };
    return { type: 'unknown', id: null };
  }

  // Count posts per category
  const categoryCounts = posts.reduce((acc, p) => {
    acc[p.category] = (acc[p.category] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  const schoolMap = new Map<number, Post>()
  posts.forEach(post => {
    if (!schoolMap.has(post.school_id)) {
      schoolMap.set(post.school_id, post)
    }
  })
  const uniqueSchools = Array.from(schoolMap.values())

  return (
    <main className="min-h-screen bg-slate-50 relative overflow-x-hidden">
      {/* ── AMBIENT BG ── */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-emerald-400/10 rounded-full blur-[140px]" />
        <div className="absolute bottom-1/3 right-1/4 w-[500px] h-[500px] bg-teal-300/8 rounded-full blur-[120px]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-sky-300/6 rounded-full blur-[160px]" />
      </div>

      {/* ── LIGHTBOX ── */}
      {lightboxIndex >= 0 && (
        <div
          className="fixed inset-0 z-[200] bg-black/95 backdrop-blur-md flex items-center justify-center p-3 sm:p-6"
          onClick={closeLightbox}
        >
          <button
            onClick={closeLightbox}
            className="absolute top-5 right-5 z-50 w-10 h-10 flex items-center justify-center rounded-full bg-white/10 hover:bg-white/20 text-white transition-all border border-white/20"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>

          <div
            className="bg-white rounded-3xl overflow-hidden flex flex-col lg:flex-row w-full max-w-6xl max-h-[92vh] shadow-[0_32px_80px_rgba(0,0,0,0.25)] border border-slate-200 relative"
            onClick={e => e.stopPropagation()}
          >
            {/* Media */}
            <div className="bg-black flex-1 relative flex items-center justify-center min-h-[42vh] lg:min-h-0">
              {activePost?.media_type === 'video_link' ? (
                <div className="w-full h-full min-h-[300px] lg:min-h-[560px] flex items-center justify-center">
                  {(() => {
                    const info = getPlatformInfo(lightboxUrls[0]);
                    if (info.type === 'youtube') return <iframe className="w-full h-full border-0" src={`https://www.youtube.com/embed/${info.id}`} allowFullScreen />;
                    if (info.type === 'tiktok') return <iframe className="w-[min(100%,400px)] h-full border-0" src={`https://www.tiktok.com/embed/v2/${info.id}`} allowFullScreen />;
                    if (info.type === 'instagram') return <iframe className="w-[min(100%,400px)] h-full border-0 bg-white" src={`https://www.instagram.com/p/${info.id}/embed`} />;
                    if (info.type === 'gdrive') return <iframe className="w-full h-full border-0" src={`https://drive.google.com/file/d/${info.id}/preview`} allowFullScreen />;
                    return (
                      <div className="text-white text-center p-6">
                        <p className="mb-4 text-lg font-semibold">Tautan video eksternal</p>
                        <a href={lightboxUrls[0]} target="_blank" rel="noopener noreferrer" className="inline-block px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 rounded-xl text-white font-bold transition-colors">
                          Buka di Tab Baru
                        </a>
                      </div>
                    );
                  })()}
                </div>
              ) : (
                <img
                  src={lightboxUrls[lightboxIndex]}
                  alt="Gallery"
                  className="max-w-full max-h-[60vh] lg:max-h-[92vh] object-contain select-none"
                />
              )}

              {lightboxUrls.length > 1 && (
                <>
                  <button
                    onClick={e => { e.stopPropagation(); setLightboxIndex(p => p > 0 ? p - 1 : lightboxUrls.length - 1) }}
                    className="absolute left-4 top-1/2 -translate-y-1/2 w-12 h-12 flex items-center justify-center rounded-full bg-black/60 hover:bg-black/80 text-white border border-white/20 backdrop-blur-md transition-all hover:scale-110"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); setLightboxIndex(p => p < lightboxUrls.length - 1 ? p + 1 : 0) }}
                    className="absolute right-4 top-1/2 -translate-y-1/2 w-12 h-12 flex items-center justify-center rounded-full bg-black/60 hover:bg-black/80 text-white border border-white/20 backdrop-blur-md transition-all hover:scale-110"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
                  </button>
                  <div className="absolute bottom-5 left-1/2 -translate-x-1/2 px-4 py-1.5 bg-black/70 rounded-full text-white/90 text-xs font-bold backdrop-blur-md border border-white/10">
                    {lightboxIndex + 1} / {lightboxUrls.length}
                  </div>
                  {/* Dot indicators */}
                  <div className="absolute bottom-12 left-1/2 -translate-x-1/2 flex gap-1.5">
                    {lightboxUrls.map((_, i) => (
                      <button
                        key={i}
                        onClick={e => { e.stopPropagation(); setLightboxIndex(i) }}
                        className={`w-2 h-2 rounded-full transition-all ${i === lightboxIndex ? 'bg-emerald-400 scale-125' : 'bg-white/30 hover:bg-white/50'}`}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Info Panel */}
            {activePost && (
              <div className="w-full lg:w-[340px] bg-white p-6 flex flex-col border-t lg:border-t-0 lg:border-l border-slate-100 overflow-y-auto">
                <div className="flex items-center gap-3 mb-5">
                  <SchoolLogoAvatar
                    name={activePost.school_name}
                    logoUrl={activePost.school_logo_url}
                    colorClass={CATEGORY_COLORS[activePost.category] || 'from-emerald-400 to-teal-600'}
                  />
                  <div className="min-w-0">
                    <a
                      href={`/sekolah/${activePost.school_id}/adiwiyata/${activePost.category}`}
                      className="font-bold text-sm text-slate-900 hover:text-emerald-600 transition-colors line-clamp-2 leading-snug"
                    >
                      {activePost.school_name}
                    </a>
                    <p className="text-xs text-emerald-600 mt-0.5 font-medium">{formatDate(activePost.created_at)}</p>
                    <p className="text-xs text-slate-400">{formatTime(activePost.created_at)}</p>
                  </div>
                </div>

                <div className="inline-flex items-center gap-2 mb-4 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200 w-fit">
                  <span className="text-sm">{CATEGORY_ICONS[activePost.category] || '🌿'}</span>
                  <span className="text-xs font-semibold text-emerald-700">{CATEGORY_LABELS[activePost.category] || activePost.category}</span>
                </div>

                <div className="flex-1 bg-slate-50 rounded-2xl p-4 border border-slate-100">
                  <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                    {activePost.description || <span className="text-slate-400 italic">Tidak ada deskripsi.</span>}
                  </p>
                </div>

                <a
                  href={`/sekolah/${activePost.school_id}/adiwiyata/${activePost.category}`}
                  className="mt-4 flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-bold text-sm hover:opacity-90 transition-all hover:scale-[1.02] shadow-lg shadow-emerald-500/25"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                  Lihat Profil Adiwiyata Sekolah
                </a>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── NAVBAR ── */}
      <nav className={`sticky top-0 w-full z-50 transition-all duration-700 ${isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4'}`}>
        <div className="bg-white/90 backdrop-blur-xl border-b border-slate-200 px-4 sm:px-8 py-4 flex items-center justify-between shadow-sm">
          <a href="/" className="flex items-center gap-3 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform">
              <span className="text-lg">🌿</span>
            </div>
            <div>
              <p className="text-sm font-black text-slate-900 leading-tight">Portal Adiwiyata</p>
              <p className="text-[10px] font-semibold text-emerald-600 uppercase tracking-widest">Sudin Pendidikan JU 2</p>
            </div>
          </a>
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-bold text-emerald-700">{posts.length} Postingan</span>
            </div>
            <a href="/" className="flex items-center gap-2 px-4 py-2 rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-900 text-sm font-semibold transition-all border border-slate-200">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
              Kembali
            </a>
          </div>
        </div>
      </nav>

      {/* ── HERO MARQUEE ── */}
      <div className={`relative w-full overflow-hidden bg-gradient-to-b from-emerald-700 to-teal-800 py-8 border-b border-emerald-900/20 transition-all duration-1000 ${isLoaded ? 'opacity-100' : 'opacity-0'}`}>
        {/* Header */}
        <div className="max-w-7xl mx-auto px-4 sm:px-8 mb-6 flex items-end justify-between">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/20 border border-white/30 text-white text-xs font-bold uppercase tracking-wider mb-3">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
              Live Feed
            </div>
            <h1 className="text-3xl sm:text-4xl font-black text-white leading-none">
              Galeri <span className="text-transparent bg-clip-text bg-gradient-to-r from-yellow-300 to-lime-300">Adiwiyata</span>
            </h1>
            <p className="text-white/70 text-sm mt-1.5 max-w-none sm:whitespace-nowrap">
              Dokumentasi aksi nyata pelestarian lingkungan sekolah-sekolah di Jakarta Utara 2.
            </p>
          </div>
          <div className="hidden sm:flex items-center gap-3">
            <div className="text-center px-4 py-3 rounded-2xl bg-white/15 border border-white/20">
              <p className="text-2xl font-black text-white">{uniqueSchools.length}</p>
              <p className="text-xs text-white/70 font-medium">Sekolah</p>
            </div>
            <div className="text-center px-4 py-3 rounded-2xl bg-white/15 border border-white/20">
              <p className="text-2xl font-black text-yellow-300">{posts.length}</p>
              <p className="text-xs text-white/70 font-medium">Postingan</p>
            </div>
          </div>
        </div>

        {/* Marquee Row 1 */}
        {photos.length > 0 && (
          <div className="relative overflow-hidden mb-3">
            <div className="flex gap-3 px-3 animate-[marqueeLeft_50s_linear_infinite] hover:[animation-play-state:paused] w-max">
              {[...photos, ...photos].map((photo, i) => (
                <div
                  key={i}
                  onClick={() => openPhotoLightbox(photo)}
                  className="relative group w-52 sm:w-64 aspect-[4/3] rounded-2xl overflow-hidden flex-shrink-0 cursor-pointer border border-white/8 bg-slate-900 shadow-lg hover:shadow-emerald-900/30 transition-shadow"
                >
                  <img src={photo.url} alt={photo.school_name} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent opacity-0 group-hover:opacity-100 transition-all duration-300 flex items-end p-3">
                    <div className="min-w-0">
                      <p className="text-white text-xs font-bold truncate leading-tight">{photo.school_name}</p>
                      <p className="text-emerald-200 text-[10px] font-semibold mt-0.5">Klik untuk lihat profil sekolah</p>
                    </div>
                  </div>
                  <div className="absolute inset-0 ring-0 group-hover:ring-2 group-hover:ring-emerald-400/60 rounded-2xl transition-all" />
                </div>
              ))}
            </div>
          </div>
        )}
        {/* Marquee Row 2 (reverse) */}
        {photos.length > 0 && (
          <div className="relative overflow-hidden">
            <div className="flex gap-3 px-3 animate-[marqueeRight_60s_linear_infinite] hover:[animation-play-state:paused] w-max">
              {[...photos.slice().reverse(), ...photos.slice().reverse()].map((photo, i) => (
                <div
                  key={i}
                  onClick={() => openPhotoLightbox(photo)}
                  className="relative group w-44 sm:w-52 aspect-[16/9] rounded-2xl overflow-hidden flex-shrink-0 cursor-pointer border border-white/8 bg-slate-900"
                >
                  <img src={photo.url} alt={photo.school_name} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-all duration-300 flex items-end p-3">
                    <div className="min-w-0">
                      <p className="text-white text-[10px] font-bold truncate">{photo.school_name}</p>
                      <p className="text-emerald-200 text-[9px] font-semibold mt-0.5">Lihat profil</p>
                    </div>
                  </div>
                  <div className="absolute inset-0 ring-0 group-hover:ring-2 group-hover:ring-teal-400/60 rounded-2xl transition-all" />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Fade edges */}
        <div className="absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-[#111827] to-transparent pointer-events-none z-10" />
        <div className="absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-[#111827] to-transparent pointer-events-none z-10" />
      </div>

      {/* ── MAIN 3-COLUMN CONTENT ── */}
      <div className="max-w-[1440px] mx-auto px-4 sm:px-8 py-8 relative z-10">
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr_280px] gap-6 xl:gap-8 items-start">

          {/* ── LEFT SIDEBAR ── */}
          <aside className={`hidden lg:flex flex-col gap-5 sticky top-24 transition-all duration-700 delay-200 ${isLoaded ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-8'}`}>
            {/* About Card */}
            <div className="rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 p-5 shadow-xl shadow-emerald-200">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-xl bg-white/25 flex items-center justify-center text-sm">🌿</div>
                <h2 className="text-sm font-black text-white">Program Adiwiyata</h2>
              </div>
              <p className="text-xs text-white/80 leading-relaxed">
                Adiwiyata adalah program pemerintah untuk mendorong sekolah peduli dan berbudaya lingkungan hidup secara berkelanjutan.
              </p>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <div className="rounded-xl bg-white/20 border border-white/30 p-3 text-center">
                  <p className="text-xl font-black text-white">{uniqueSchools.length}</p>
                  <p className="text-[10px] text-white/70 font-medium">Sekolah</p>
                </div>
                <div className="rounded-xl bg-white/20 border border-white/30 p-3 text-center">
                  <p className="text-xl font-black text-yellow-200">{posts.length}</p>
                  <p className="text-[10px] text-white/70 font-medium">Postingan</p>
                </div>
              </div>
            </div>

            {/* Category Stats */}
            <div className="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm">
              <h2 className="text-sm font-black text-slate-800 mb-4 flex items-center gap-2">
                <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>
                Kategori
              </h2>
              <div className="space-y-3">
                {Object.entries(CATEGORY_LABELS).map(([key, label]) => {
                  const count = categoryCounts[key] || 0
                  const maxCount = Math.max(...Object.values(categoryCounts), 1)
                  return (
                    <div key={key} className="group">
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm">{CATEGORY_ICONS[key]}</span>
                          <span className="text-xs font-semibold text-slate-600 group-hover:text-slate-900 transition-colors truncate max-w-[140px]">{label}</span>
                        </div>
                        <span className="text-[10px] font-bold text-slate-400">{count}</span>
                      </div>
                      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full bg-gradient-to-r ${CATEGORY_COLORS[key]} transition-all duration-1000`}
                          style={{ width: `${(count / maxCount) * 100}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Schools List */}
            <div className="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm">
              <h2 className="text-sm font-black text-slate-800 mb-4 flex items-center gap-2">
                <svg className="w-4 h-4 text-sky-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
                Sekolah Aktif
              </h2>
              <div className="space-y-1 max-h-64 overflow-y-auto pr-1 custom-scroll">
                {uniqueSchools.slice(0, 15).map((schoolPost, i) => {
                  return (
                    <a
                      key={i}
                      href={`/sekolah/${schoolPost.school_id}/adiwiyata/${schoolPost.category}`}
                      className="flex items-center gap-2.5 p-2 rounded-xl hover:bg-emerald-50 transition-colors group cursor-pointer"
                    >
                      <SchoolLogoAvatar
                        name={schoolPost.school_name}
                        logoUrl={schoolPost.school_logo_url}
                        colorClass={CATEGORY_COLORS[schoolPost.category] || 'from-green-400 to-emerald-600'}
                        className="w-7 h-7 rounded-lg text-xs"
                      />
                      <span className="text-xs text-slate-500 group-hover:text-slate-800 transition-colors font-medium leading-tight line-clamp-2">{schoolPost.school_name}</span>
                    </a>
                  )
                })}
              </div>
            </div>
          </aside>

          {/* ── TIMELINE FEED ── */}
          <section className={`transition-all duration-700 ${isLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-black text-slate-900">Lini Masa</h2>
                <p className="text-xs text-slate-500 mt-0.5">Pembaruan terbaru dari seluruh sekolah</p>
              </div>
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-xs font-bold text-emerald-700">Terbaru</span>
              </div>
            </div>

            <div className="space-y-5">
              {posts.map((post, idx) => {
                const isVisible = visiblePosts.has(post.id)
                const catColor = CATEGORY_COLORS[post.category] || 'from-emerald-400 to-teal-600'
                const catIcon = CATEGORY_ICONS[post.category] || '🌿'
                const urls = post.media_urls || (post.media_path ? [post.media_path] : [])
                return (
                  <div
                    key={post.id}
                    ref={el => registerPostRef(el, post.id)}
                    data-postid={post.id}
                    className={`rounded-3xl bg-white border border-slate-200 overflow-hidden hover:border-emerald-200 hover:shadow-lg transition-all duration-700 shadow-sm ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}
                    style={{ transitionDelay: `${Math.min(idx * 50, 300)}ms` }}
                  >
                    {/* Post Header */}
                    <div className="flex items-center gap-3 px-5 pt-5 pb-4 border-b border-slate-100">
                      <SchoolLogoAvatar
                        name={post.school_name}
                        logoUrl={post.school_logo_url}
                        colorClass={catColor}
                        className="w-12 h-12 rounded-2xl text-base"
                      />
                      <div className="flex-1 min-w-0">
                        <a
                          href={`/sekolah/${post.school_id}/adiwiyata/${post.category}`}
                          className="block font-black text-sm sm:text-base text-slate-900 hover:text-emerald-600 transition-colors truncate leading-tight"
                        >
                          {post.school_name}
                        </a>
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 border border-emerald-200 text-[10px] font-bold text-emerald-700">
                            <span>{catIcon}</span>{CATEGORY_LABELS[post.category] || post.category}
                          </span>
                          <span className="text-[10px] text-slate-400">{formatDate(post.created_at)}</span>
                        </div>
                      </div>
                    </div>

                    {/* Description */}
                    {post.description && (
                      <div className="px-5 py-4">
                        <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap">{post.description}</p>
                      </div>
                    )}

                    {/* Media */}
                    {post.media_type === 'image' && urls.length > 0 && (
                      <div
                        className="relative cursor-pointer group overflow-hidden aspect-[16/9]"
                        onClick={() => openLightbox(urls, 0, post)}
                      >
                        <img
                          src={urls[0]}
                          alt="Post"
                          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                        />
                        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
                        {urls.length > 1 && (
                          <div className="absolute top-3 right-3 flex items-center gap-1.5 px-2.5 py-1.5 bg-black/70 backdrop-blur-md rounded-lg border border-white/10">
                            <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                            <span className="text-white text-xs font-bold">{urls.length}</span>
                          </div>
                        )}
                        {/* Click hint */}
                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                          <div className="px-3 py-1.5 bg-black/60 backdrop-blur-md rounded-full text-white text-xs font-bold border border-white/20">
                            Klik untuk memperbesar
                          </div>
                        </div>
                      </div>
                    )}

                    {post.media_type === 'video_link' && post.media_path && (
                      <div
                        className="relative aspect-video cursor-pointer group overflow-hidden"
                        onClick={() => openLightbox([post.media_path!], 0, post)}
                      >
                        {(() => {
                          const info = getPlatformInfo(post.media_path);
                          if (info.type === 'youtube') {
                            return (
                              <>
                                <img
                                  src={`https://img.youtube.com/vi/${info.id}/maxresdefault.jpg`}
                                  alt="Video"
                                  className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                                  onError={e => { (e.target as HTMLImageElement).src = `https://img.youtube.com/vi/${info.id}/hqdefault.jpg` }}
                                />
                                <div className="absolute inset-0 bg-black/30 group-hover:bg-black/50 transition-colors flex items-center justify-center">
                                  <div className="w-16 h-16 rounded-full bg-red-600 flex items-center justify-center shadow-2xl group-hover:scale-110 transition-transform">
                                    <svg className="w-7 h-7 text-white ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                                  </div>
                                </div>
                              </>
                            )
                          } else if (info.type === 'tiktok') {
                            return (
                              <div className="w-full h-full bg-[#010101] flex items-center justify-center transition-transform duration-700 group-hover:scale-105">
                                <div className="text-center text-white">
                                  <svg className="w-12 h-12 mx-auto mb-3" viewBox="0 0 448 512" fill="currentColor"><path d="M448 209.91a210.06 210.06 0 0 1-122.77-39.25V349.38A162.55 162.55 0 1 1 185 188.31v89.89a74.62 74.62 0 1 0 52.23 71.18V0l88 0a121.18 121.18 0 0 0 1.86 22.17h0A122.18 122.18 0 0 0 381 102.39a121.43 121.43 0 0 0 67 20.14Z"/></svg>
                                  <span className="font-bold tracking-wide">TikTok Video</span>
                                </div>
                              </div>
                            )
                          } else if (info.type === 'instagram') {
                            return (
                              <div className="w-full h-full bg-gradient-to-tr from-yellow-400 via-pink-500 to-purple-600 flex items-center justify-center transition-transform duration-700 group-hover:scale-105">
                                <div className="text-center text-white">
                                  <svg className="w-12 h-12 mx-auto mb-3" viewBox="0 0 448 512" fill="currentColor"><path d="M224.1 141c-63.6 0-114.9 51.3-114.9 114.9s51.3 114.9 114.9 114.9S339 319.5 339 255.9 287.7 141 224.1 141zm0 189.6c-41.1 0-74.7-33.5-74.7-74.7s33.5-74.7 74.7-74.7 74.7 33.5 74.7 74.7-33.6 74.7-74.7 74.7zm146.4-194.3c0 14.9-12 26.8-26.8 26.8-14.9 0-26.8-12-26.8-26.8s12-26.8 26.8-26.8 26.8 12 26.8 26.8zm76.1 27.2c-1.7-35.9-9.9-67.7-36.2-93.9-26.2-26.2-58-34.4-93.9-36.2-37-2.1-147.9-2.1-184.9 0-35.8 1.7-67.6 9.9-93.9 36.1s-34.4 58-36.2 93.9c-2.1 37-2.1 147.9 0 184.9 1.7 35.9 9.9 67.7 36.2 93.9s58 34.4 93.9 36.2c37 2.1 147.9 2.1 184.9 0 35.9-1.7 67.7-9.9 93.9-36.2 26.2-26.2 34.4-58 36.2-93.9 2.1-37 2.1-147.8 0-184.8zM398.8 388c-7.8 19.6-22.9 34.7-42.6 42.6-29.5 11.7-99.5 9-132.1 9s-102.7 2.6-132.1-9c-19.6-7.8-34.7-22.9-42.6-42.6-11.7-29.5-9-99.5-9-132.1s-2.6-102.7 9-132.1c7.8-19.6 22.9-34.7 42.6-42.6 29.5-11.7 99.5-9 132.1-9s102.7-2.6 132.1 9c19.6 7.8 34.7 22.9 42.6 42.6 11.7 29.5 9 99.5 9 132.1s2.7 102.7-9 132.1z"/></svg>
                                  <span className="font-bold tracking-wide">Instagram</span>
                                </div>
                              </div>
                            )
                          } else if (info.type === 'gdrive') {
                            return (
                              <div className="w-full h-full bg-slate-100 flex items-center justify-center transition-transform duration-700 group-hover:scale-105">
                                <div className="text-center text-[#1A73E8]">
                                  <svg className="w-12 h-12 mx-auto mb-3" viewBox="0 0 512 512" fill="currentColor"><path d="M339 314.9L175.4 32h161.2l163.6 282.9H339zm-137.5 23.6L120.9 480h310.5L512 338.5H201.5zM154.1 67.4L0 338.5 82.6 480 236.7 208.8 154.1 67.4z"/></svg>
                                  <span className="font-bold tracking-wide">Google Drive</span>
                                </div>
                              </div>
                            )
                          } else {
                            return (
                              <div className="w-full h-full bg-slate-900 flex items-center justify-center transition-transform duration-700 group-hover:scale-105">
                                <div className="text-center">
                                  <div className="w-16 h-16 rounded-full bg-sky-600 flex items-center justify-center mx-auto mb-3 shadow-lg">
                                    <svg className="w-7 h-7 text-white ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                                  </div>
                                  <p className="text-white text-sm font-bold">Putar Video</p>
                                </div>
                              </div>
                            )
                          }
                        })()}
                      </div>
                    )}

                    {/* Post Footer */}
                    <div className="px-5 py-3.5 flex items-center justify-between border-t border-slate-100 bg-white">
                      <span className="text-[11px] text-slate-400 font-medium">{formatTime(post.created_at)}</span>
                      <a
                        href={`/sekolah/${post.school_id}/adiwiyata/${post.category}`}
                        className="flex items-center gap-1.5 text-[11px] font-bold text-emerald-600 hover:text-emerald-700 transition-colors"
                      >
                        Lihat Profil Adiwiyata
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
                      </a>
                    </div>
                    
                    {/* Likes and Comments */}
                    <PostActions postId={post.id} />
                  </div>
                )
              })}
            </div>

            {/* Loading / Load More */}
            {isLoading && (
              <div className="flex flex-col items-center gap-4 py-12">
                <div className="relative w-12 h-12">
                  <div className="absolute inset-0 rounded-full border-4 border-emerald-200" />
                  <div className="absolute inset-0 rounded-full border-4 border-t-emerald-500 border-r-transparent border-b-transparent border-l-transparent animate-spin" />
                </div>
                <p className="text-sm text-slate-500 font-medium">Memuat postingan…</p>
              </div>
            )}

            {!isLoading && hasMore && (
              <div className="flex justify-center pt-6 pb-12">
                <button
                  onClick={loadMore}
                  className="group flex items-center gap-3 px-8 py-3.5 rounded-2xl bg-white hover:bg-emerald-50 border border-slate-200 hover:border-emerald-300 text-slate-600 hover:text-emerald-700 font-bold text-sm transition-all duration-300 hover:shadow-lg hover:shadow-emerald-100 shadow-sm"
                >
                  <svg className="w-5 h-5 group-hover:animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" /></svg>
                  Muat Lebih Banyak
                </button>
              </div>
            )}

            {!isLoading && !hasMore && posts.length > 0 && (
              <div className="text-center py-12">
                <div className="w-8 h-0.5 bg-slate-200 mx-auto mb-4 rounded-full" />
                <p className="text-sm text-slate-400 font-medium">Semua postingan sudah ditampilkan</p>
              </div>
            )}

            {!isLoading && posts.length === 0 && (
              <div className="text-center py-24">
                <div className="text-5xl mb-4">🌿</div>
                <h3 className="text-slate-700 font-bold text-xl mb-2">Belum Ada Postingan</h3>
                <p className="text-slate-400 text-sm">Sekolah belum mengunggah dokumentasi Adiwiyata.</p>
              </div>
            )}
          </section>

          {/* ── RIGHT SIDEBAR ── */}
          <aside className={`hidden lg:flex flex-col gap-5 sticky top-24 transition-all duration-700 delay-300 ${isLoaded ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-8'}`}>
            {/* Live Photos */}
            <div className="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm">
              <h2 className="text-sm font-black text-slate-800 mb-4 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                Foto Terbaru
              </h2>
              <div className="grid grid-cols-2 gap-2">
                {photos.slice(0, 6).map((photo, i) => (
                  <div
                    key={i}
                    onClick={() => openPhotoLightbox(photo)}
                    className="relative aspect-square rounded-xl overflow-hidden cursor-pointer group bg-slate-100 border border-slate-200"
                  >
                    <img src={photo.url} alt={photo.school_name} className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" />
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/45 transition-colors" />
                    <div className="absolute inset-x-0 bottom-0 p-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <p className="text-white text-[10px] font-bold leading-tight truncate">{photo.school_name}</p>
                    </div>
                    <div className="absolute inset-0 ring-0 group-hover:ring-2 group-hover:ring-emerald-400 rounded-xl transition-all" />
                  </div>
                ))}
              </div>
            </div>

            {/* Kategori Quick Nav */}
            <div className="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm">
              <h2 className="text-sm font-black text-slate-800 mb-4">Jelajahi Kategori</h2>
              <div className="space-y-2">
                {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
                  <div
                    key={key}
                    className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200 hover:border-emerald-300 hover:bg-emerald-50 transition-all cursor-pointer group"
                  >
                    <span className="text-xl">{CATEGORY_ICONS[key]}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-bold text-slate-700 group-hover:text-slate-900 transition-colors truncate">{label}</p>
                      <p className="text-[10px] text-slate-400">{categoryCounts[key] || 0} postingan</p>
                    </div>
                    <div className={`w-2 h-2 rounded-full bg-gradient-to-br ${CATEGORY_COLORS[key]}`} />
                  </div>
                ))}
              </div>
            </div>

            {/* Info Card */}
            <div className="rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 p-5 shadow-lg shadow-emerald-200">
              <div className="text-2xl mb-3">🏆</div>
              <h3 className="text-sm font-black text-white mb-2">Tentang Adiwiyata</h3>
              <p className="text-xs text-white/80 leading-relaxed">
                Program Adiwiyata bertujuan mewujudkan warga sekolah yang bertanggung jawab dalam upaya perlindungan dan pengelolaan lingkungan hidup.
              </p>
              <div className="mt-4 pt-4 border-t border-white/20">
                <p className="text-[10px] text-white/60 font-semibold uppercase tracking-widest">Dinas Pendidikan</p>
                <p className="text-xs text-white font-bold">Jakarta Utara 2</p>
              </div>
            </div>
          </aside>
        </div>
      </div>

      {/* Global Styles */}
      <style>{`
        @keyframes marqueeLeft {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @keyframes marqueeRight {
          0% { transform: translateX(-50%); }
          100% { transform: translateX(0); }
        }
        .custom-scroll::-webkit-scrollbar { width: 4px; }
        .custom-scroll::-webkit-scrollbar-track { background: transparent; }
        .custom-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 999px; }
        .custom-scroll::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
      `}</style>
    </main>
  )
}
