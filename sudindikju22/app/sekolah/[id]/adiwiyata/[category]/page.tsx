'use client'

import React, { useEffect, useState } from 'react'

interface Post {
  id: number;
  school_id: number;
  category: string;
  media_type: string;
  media_urls: string[] | null;
  media_path: string | null;
  description: string;
  created_at: string;
}

export default function PublicSchoolAdiwiyataPage({ params }: { params: Promise<{ id: string, category: string }> }) {
  const resolvedParams = React.use(params);
  
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState('')
  const [school, setSchool] = useState<any>(null)
  const [posts, setPosts] = useState<Post[]>([])
  const [title, setTitle] = useState('')
  
  const [lightboxIndex, setLightboxIndex] = useState(-1)
  const [lightboxUrls, setLightboxUrls] = useState<string[]>([])
  const [activePost, setActivePost] = useState<Post | null>(null)

  const [imgError, setImgError] = useState(false)

  useEffect(() => {
    fetch(`http://127.0.0.1:5002/portal/api/public/sekolah/${resolvedParams.id}/adiwiyata/${resolvedParams.category}`)
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setSchool(data.school)
          setPosts(data.posts)
          setTitle(data.title)
          setImgError(false)
        } else {
          setErrorMsg(data.message || 'Gagal memuat profil sekolah.')
        }
      })
      .catch(() => setErrorMsg('Gagal terhubung ke server.'))
      .finally(() => setLoading(false))
  }, [resolvedParams.id, resolvedParams.category])

  const openLightbox = (urls: string[], idx = 0, post: Post | null = null) => {
    setLightboxUrls(urls)
    setLightboxIndex(idx)
    setActivePost(post)
    document.body.style.overflow = 'hidden'
  }

  const closeLightbox = () => {
    setLightboxIndex(-1)
    setActivePost(null)
    document.body.style.overflow = ''
  }

  const getPlatformInfo = (url: string) => {
    if (!url) return { type: 'unknown', id: null };
    
    // YouTube
    const ytMatch = url.match(/(?:youtube\.com\/(?:[^/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?/\s]{11})/i);
    if (ytMatch) return { type: 'youtube', id: ytMatch[1] };
    
    // TikTok
    const ttMatch = url.match(/(?:tiktok\.com\/.*\/video\/|tiktok\.com\/v\/|vt\.tiktok\.com\/)([\w\d]+)/i);
    if (ttMatch) return { type: 'tiktok', id: ttMatch[1] };
    
    // Instagram
    const igMatch = url.match(/instagram\.com\/(?:p|reel|tv)\/([A-Za-z0-9_-]+)/i);
    if (igMatch) return { type: 'instagram', id: igMatch[1] };
    
    // Google Drive
    const gdMatch = url.match(/drive\.google\.com\/(?:file\/d\/|open\?id=)([\w-]+)/i);
    if (gdMatch) return { type: 'gdrive', id: gdMatch[1] };
    
    return { type: 'unknown', id: null };
  }

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' })
  }

  const formatTime = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) + ' WIB'
  }

  const getFullUrl = (url: string | null) => {
    if (!url) return '';
    if (url.startsWith('http://') || url.startsWith('https://')) return url;
    if (url.startsWith('/')) return `http://127.0.0.1:5002${url}`;
    return `http://127.0.0.1:5002/portal/uploads/${url}`;
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f0f2f5]">
        <div className="text-sm font-semibold text-slate-500">Memuat profil sekolah...</div>
      </div>
    )
  }

  if (errorMsg) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f0f2f5] p-6">
        <div className="bg-white p-8 rounded-[18px] border border-gray-200 shadow-sm max-w-md text-center w-full">
          <h2 className="text-xl font-bold text-gray-800 mb-2">Terjadi Kesalahan</h2>
          <p className="text-gray-500 mb-6 text-sm">{errorMsg}</p>
          <a href="/adiwiyata" className="inline-block px-5 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold rounded-lg transition-colors text-sm">Kembali ke Galeri</a>
        </div>
      </div>
    )
  }

  return (
    <main className="min-h-screen bg-[#f0f2f5] font-['Plus_Jakarta_Sans',sans-serif] text-slate-800 pb-16">
      
      {/* Lightbox / Modal */}
      {lightboxIndex >= 0 && (
        <div className="fixed inset-0 z-[1050] bg-black/90 flex items-center justify-center" onClick={closeLightbox}>
          <div className="bg-white rounded-[18px] overflow-hidden flex flex-col md:flex-row max-w-[90vw] max-h-[90vh] shadow-2xl" onClick={e => e.stopPropagation()}>
            {/* Media Area */}
            <div className="bg-black relative flex items-center justify-center w-full md:w-[min(55vw,820px)] h-[min(90vh,760px)] min-w-[320px] min-h-[360px]">
              {activePost?.media_type === 'video_link' ? (
                <div className="w-full h-full min-h-[320px] flex items-center justify-center">
                  {(() => {
                    const info = getPlatformInfo(lightboxUrls[0]);
                    if (info.type === 'youtube') return <iframe className="w-full h-full border-0" src={`https://www.youtube.com/embed/${info.id}`} allowFullScreen />;
                    if (info.type === 'tiktok') return <iframe className="w-[min(100%,400px)] h-full border-0" src={`https://www.tiktok.com/embed/v2/${info.id}`} allowFullScreen />;
                    if (info.type === 'instagram') return <iframe className="w-[min(100%,400px)] h-full border-0 bg-white" src={`https://www.instagram.com/p/${info.id}/embed`} />;
                    if (info.type === 'gdrive') return <iframe className="w-full h-full border-0" src={`https://drive.google.com/file/d/${info.id}/preview`} allowFullScreen />;
                    return (
                      <div className="text-white text-center p-6">
                        <p className="mb-4 text-lg font-semibold">Tautan video eksternal</p>
                        <a href={lightboxUrls[0]} target="_blank" rel="noopener noreferrer" className="inline-block px-5 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-bold transition-colors">
                          Buka di Tab Baru
                        </a>
                      </div>
                    );
                  })()}
                </div>
              ) : (
                <img src={lightboxUrls[lightboxIndex]} alt="Gallery" className="max-w-full max-h-full object-contain block" />
              )}
              
              {/* Controls */}
              <button onClick={closeLightbox} className="absolute top-3 right-4 bg-black/50 hover:bg-black/80 text-white w-8 h-8 rounded-full flex items-center justify-center transition-colors">
                ✕
              </button>
              
              {lightboxUrls.length > 1 && (
                <>
                  <button onClick={e => { e.stopPropagation(); setLightboxIndex(p => p > 0 ? p - 1 : lightboxUrls.length - 1) }} className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-full bg-black/50 hover:bg-black/70 text-white transition-all text-xl">
                    ‹
                  </button>
                  <button onClick={e => { e.stopPropagation(); setLightboxIndex(p => p < lightboxUrls.length - 1 ? p + 1 : 0) }} className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-full bg-black/50 hover:bg-black/70 text-white transition-all text-xl">
                    ›
                  </button>
                  <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-black/50 text-white px-3 py-1 rounded-full text-xs font-bold">
                    {lightboxIndex + 1} / {lightboxUrls.length}
                  </div>
                </>
              )}
            </div>
            
            {/* Info Area */}
            {activePost && (
              <div className="w-full md:w-[340px] p-5 flex flex-col overflow-y-auto bg-white max-h-[38vh] md:max-h-none">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-green-600 to-green-700 text-white font-extrabold flex items-center justify-center text-lg flex-shrink-0">
                    {school.name.charAt(0)}
                  </div>
                  <div>
                    <h4 className="font-extrabold text-sm m-0 leading-tight">{school.name}</h4>
                    <p className="text-xs text-gray-500 mt-0.5">{formatDate(activePost.created_at)} • {formatTime(activePost.created_at)}</p>
                  </div>
                </div>
                <div className="text-sm text-gray-800 whitespace-pre-line leading-relaxed flex-1">
                  {activePost.description || <span className="text-gray-400 italic">Tidak ada deskripsi.</span>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Topbar */}
      <div className="bg-white border-b border-gray-200 px-5 h-14 flex items-center sticky top-0 z-50 shadow-sm gap-3">
        <a href="/adiwiyata" className="flex items-center gap-1.5 text-gray-500 hover:text-green-600 hover:bg-green-100 border border-gray-200 hover:border-green-600 px-2.5 py-1.5 rounded-lg text-sm font-semibold transition-all">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
          Kembali
        </a>
        <div className="flex-1 font-bold text-gray-900 flex items-center gap-2 text-base">
          <div className="w-[30px] h-[30px] rounded-lg bg-green-600 text-white flex items-center justify-center text-sm">
            🌿
          </div>
          {title}
        </div>
      </div>

      <div className="max-w-[900px] mx-auto px-4 mt-6">
        
        {/* Profile Card */}
        <div className="bg-white border border-gray-200 rounded-[18px] shadow-sm mb-6">
          <div className="flex flex-col sm:flex-row items-center sm:items-start p-5 gap-4">
            <div className="w-[74px] h-[74px] rounded-[18px] bg-white border border-gray-200 text-gray-400 font-black text-2xl flex items-center justify-center flex-shrink-0 shadow-[0_4px_12px_rgba(0,0,0,0.05)] overflow-hidden">
              {school.logo_url && !imgError ? (
                <img src={getFullUrl(school.logo_url)} alt="Logo" onError={() => setImgError(true)} className="w-full h-full object-contain p-1 bg-white" />
              ) : (
                school.name.charAt(0)
              )}
            </div>
            
            <div className="flex-1 text-center sm:text-left">
              <div className="inline-flex items-center px-3 py-1 rounded-full bg-green-100/70 text-green-700 text-xs font-bold tracking-wide mb-2.5">
                <svg className="w-3.5 h-3.5 mr-1" fill="currentColor" viewBox="0 0 16 16"><path d="M8.416.223a.5.5 0 0 0-.832 0l-3 4.5A.5.5 0 0 0 5 5.5h.098L3.076 8.735A.5.5 0 0 0 3.5 9.5h.191l-1.638 3.276a.5.5 0 0 0 .447.724H7V16h2v-2.5h4.5a.5.5 0 0 0 .447-.724L12.31 9.5h.191a.5.5 0 0 0 .424-.765L10.902 5.5H11a.5.5 0 0 0 .416-.777l-3-4.5z"/></svg>
                Profil Adiwiyata Sekolah
              </div>
              <h1 className="text-xl font-bold text-slate-900 leading-tight m-0">{school.name}</h1>
              
              <div className="flex flex-wrap items-center justify-center sm:justify-start gap-x-3 gap-y-1.5 mt-2.5 text-[13px] font-semibold text-slate-500">
                {school.npsn && <span># NPSN {school.npsn}</span>}
                {school.jenjang && <span className="flex items-center gap-1"><svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 16 16"><path d="M8 1.113a5.111 5.111 0 0 0-5.111 5.111c0 2.222 1.34 4.092 3.256 4.808v1.854c0 .35.282.635.632.635h2.446a.634.634 0 0 0 .633-.635v-1.854c1.916-.716 3.255-2.586 3.255-4.808A5.111 5.111 0 0 0 8 1.113zM6.889 13.5v1.389A.611.611 0 0 0 7.5 15.5h1a.611.611 0 0 0 .611-.611V13.5H6.889z"/></svg>{school.jenjang}</span>}
                {school.status && <span className="flex items-center gap-1"><svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 16 16"><path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425a.267.267 0 0 1 .02-.022z"/></svg>{school.status}</span>}
                {school.public_location && <span className="flex items-center gap-1"><svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 16 16"><path d="M8 16s6-5.686 6-10A6 6 0 0 0 2 6c0 4.314 6 10 6 10zm0-7a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"/></svg>{school.public_location}</span>}
              </div>
              
              {school.alamat && (
                <p className="mt-3 text-[13px] text-slate-500 leading-relaxed">
                  {school.alamat}
                </p>
              )}
            </div>
          </div>
          
          {school.public_stats && school.public_stats.length > 0 && (
            <div className="flex border-t border-gray-200 bg-gray-50/50 overflow-x-auto">
              {school.public_stats.map((stat: any, i: number) => (
                <div key={i} className="px-5 py-4 min-w-[90px] border-r border-gray-200 last:border-r-0">
                  <strong className="block text-lg font-bold text-slate-900 leading-none mb-1.5">{stat.value}</strong>
                  <span className="block text-[11px] font-semibold text-slate-500">{stat.label}</span>
                </div>
              ))}
            </div>
          )}

          {(school.public_contacts?.length > 0 || school.public_links?.length > 0) && (
            <div className="flex flex-wrap items-center gap-2.5 p-4 border-t border-gray-200">
              {school.public_contacts?.map((contact: any, i: number) => (
                <a key={`c-${i}`} href={contact.href} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-300 text-slate-700 hover:text-green-700 hover:border-green-600 hover:bg-green-50 text-[12px] font-semibold transition-all">
                  {contact.label}
                </a>
              ))}
              {school.public_links?.map((link: any, i: number) => (
                <a key={`l-${i}`} href={link.href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-300 text-slate-700 hover:text-green-700 hover:border-green-600 hover:bg-green-50 text-[12px] font-semibold transition-all">
                  {link.label}
                </a>
              ))}
            </div>
          )}
        </div>

        {/* Gallery */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[15px] font-bold text-slate-900 flex items-center gap-2">
              <svg className="w-4 h-4 text-green-600" fill="currentColor" viewBox="0 0 16 16">
                <path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h3A1.5 1.5 0 0 1 7 2.5v3A1.5 1.5 0 0 1 5.5 7h-3A1.5 1.5 0 0 1 1 5.5v-3zM2.5 2a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3zm6.5.5A1.5 1.5 0 0 1 10.5 1h3A1.5 1.5 0 0 1 15 2.5v3A1.5 1.5 0 0 1 13.5 7h-3A1.5 1.5 0 0 1 9 5.5v-3zm1.5-.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3zM1 10.5A1.5 1.5 0 0 1 2.5 9h3A1.5 1.5 0 0 1 7 10.5v3A1.5 1.5 0 0 1 5.5 15h-3A1.5 1.5 0 0 1 1 13.5v-3zm1.5-.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3zm6.5.5A1.5 1.5 0 0 1 10.5 9h3a1.5 1.5 0 0 1 1.5 1.5v3a1.5 1.5 0 0 1-1.5 1.5h-3A1.5 1.5 0 0 1 9 13.5v-3zm1.5-.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3z"/>
              </svg>
              Galeri Dokumentasi
            </h2>
            {posts.length > 0 && (
              <div className="bg-[#16a34a] text-white px-2.5 py-1 rounded-full text-xs font-bold shadow-sm">
                {posts.length} Postingan
              </div>
            )}
          </div>

          {posts.length === 0 ? (
            <div className="bg-white border border-gray-200 rounded-[18px] p-14 text-center">
              <div className="text-[56px] text-gray-300 mb-3">🖼️</div>
              <h3 className="text-[17px] font-extrabold mb-1.5">Belum ada dokumentasi</h3>
              <p className="text-[13px] text-gray-500">Sekolah ini belum memposting dokumentasi <strong className="text-gray-700">{title}</strong>.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-[3px] rounded-[14px] overflow-hidden">
              {posts.map(post => {
                const rawUrls = post.media_urls || (post.media_path ? [post.media_path] : [])
                const urls = rawUrls.map(u => getFullUrl(u))
                
                if (post.media_type === 'video_link' && urls.length > 0) {
                  const info = getPlatformInfo(rawUrls[0] || '');
                  let thumbContent = null;
                  let bgClass = "bg-gray-100";
                  
                  if (info.type === 'youtube') {
                    thumbContent = <img src={`https://img.youtube.com/vi/${info.id}/hqdefault.jpg`} alt="Video" className="w-full h-full object-cover" />;
                  } else if (info.type === 'tiktok') {
                    bgClass = "bg-[#010101] text-white";
                    thumbContent = <div className="flex flex-col items-center justify-center h-full"><svg className="w-10 h-10 mb-2" viewBox="0 0 448 512" fill="currentColor"><path d="M448 209.91a210.06 210.06 0 0 1-122.77-39.25V349.38A162.55 162.55 0 1 1 185 188.31v89.89a74.62 74.62 0 1 0 52.23 71.18V0l88 0a121.18 121.18 0 0 0 1.86 22.17h0A122.18 122.18 0 0 0 381 102.39a121.43 121.43 0 0 0 67 20.14Z"/></svg><span className="font-bold text-[11px] tracking-wide">TikTok Video</span></div>;
                  } else if (info.type === 'instagram') {
                    bgClass = "bg-gradient-to-tr from-yellow-400 via-pink-500 to-purple-600 text-white";
                    thumbContent = <div className="flex flex-col items-center justify-center h-full"><svg className="w-10 h-10 mb-2" viewBox="0 0 448 512" fill="currentColor"><path d="M224.1 141c-63.6 0-114.9 51.3-114.9 114.9s51.3 114.9 114.9 114.9S339 319.5 339 255.9 287.7 141 224.1 141zm0 189.6c-41.1 0-74.7-33.5-74.7-74.7s33.5-74.7 74.7-74.7 74.7 33.5 74.7 74.7-33.6 74.7-74.7 74.7zm146.4-194.3c0 14.9-12 26.8-26.8 26.8-14.9 0-26.8-12-26.8-26.8s12-26.8 26.8-26.8 26.8 12 26.8 26.8zm76.1 27.2c-1.7-35.9-9.9-67.7-36.2-93.9-26.2-26.2-58-34.4-93.9-36.2-37-2.1-147.9-2.1-184.9 0-35.8 1.7-67.6 9.9-93.9 36.1s-34.4 58-36.2 93.9c-2.1 37-2.1 147.9 0 184.9 1.7 35.9 9.9 67.7 36.2 93.9s58 34.4 93.9 36.2c37 2.1 147.9 2.1 184.9 0 35.9-1.7 67.7-9.9 93.9-36.2 26.2-26.2 34.4-58 36.2-93.9 2.1-37 2.1-147.8 0-184.8zM398.8 388c-7.8 19.6-22.9 34.7-42.6 42.6-29.5 11.7-99.5 9-132.1 9s-102.7 2.6-132.1-9c-19.6-7.8-34.7-22.9-42.6-42.6-11.7-29.5-9-99.5-9-132.1s-2.6-102.7 9-132.1c7.8-19.6 22.9-34.7 42.6-42.6 29.5-11.7 99.5-9 132.1-9s102.7-2.6 132.1 9c19.6 7.8 34.7 22.9 42.6 42.6 11.7 29.5 9 99.5 9 132.1s2.7 102.7-9 132.1z"/></svg><span className="font-bold text-[11px] tracking-wide">Instagram</span></div>;
                  } else if (info.type === 'gdrive') {
                    bgClass = "bg-white border border-gray-200 text-[#1A73E8]";
                    thumbContent = <div className="flex flex-col items-center justify-center h-full"><svg className="w-10 h-10 mb-2" viewBox="0 0 512 512" fill="currentColor"><path d="M339 314.9L175.4 32h161.2l163.6 282.9H339zm-137.5 23.6L120.9 480h310.5L512 338.5H201.5zM154.1 67.4L0 338.5 82.6 480 236.7 208.8 154.1 67.4z"/></svg><span className="font-bold text-[11px] tracking-wide text-gray-700">Google Drive</span></div>;
                  } else {
                    bgClass = "bg-blue-600 text-white";
                    thumbContent = <div className="flex flex-col items-center justify-center h-full"><span className="text-3xl mb-2">🔗</span><span className="font-bold text-[11px] tracking-wide">Buka Tautan</span></div>;
                  }

                  return (
                    <div key={post.id} className="aspect-square relative cursor-pointer group" onClick={() => openLightbox(urls, 0, post)}>
                      <div className={`absolute inset-0 flex items-center justify-center ${bgClass}`}>
                        {thumbContent}
                      </div>
                      <div className="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] font-extrabold px-2 py-1 rounded shadow-sm flex items-center gap-1.5">
                        ▶
                      </div>
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors pointer-events-none" />
                    </div>
                  )
                }

                return (
                  <div 
                    key={post.id} 
                    className="relative aspect-square cursor-pointer overflow-hidden bg-gray-200 group"
                    onClick={() => openLightbox(urls, 0, post)}
                  >
                    {post.media_type === 'image' && urls.length > 0 && (
                      <>
                        <img src={urls[0]} alt="Post" className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" loading="lazy" />
                        {urls.length > 1 && (
                          <div className="absolute top-2 right-2 bg-black/60 text-white px-2 py-0.5 rounded-full text-[11px] font-extrabold z-10 flex items-center gap-1">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                            {urls.length}
                          </div>
                        )}
                      </>
                    )}
                    

                    
                    <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-2.5 pt-6 translate-y-full transition-transform duration-250 ease-out group-hover:translate-y-0">
                      {post.description && (
                        <p className="text-[11px] text-white/90 leading-tight line-clamp-2 mb-1">{post.description}</p>
                      )}
                      <p className="text-[10px] text-white/70">{formatDate(post.created_at)}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </main>
  )
}
