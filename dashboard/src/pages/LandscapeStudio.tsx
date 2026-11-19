import { useCallback, useEffect, useRef, useState } from 'react'
import { Aperture, Camera, ChevronDown, Download, Film, LoaderCircle, Pause, Play, Settings2 } from 'lucide-react'
import { AdaptiveStatusPanel, PerformanceSettingsPanel, type AdaptiveStatus, type PerformanceSettings } from './PerformancePanel'
import MusePage, { Media } from './MusePage'
import { API_BASE_URL } from '../api/client'

type Performance = PerformanceSettings
type CameraOption = { id: string; label: string; description?: string }
type Scene = { id: string; number: number; title: string; camera: string; image_prompt: string; video_prompt: string; image: string | null; video: string | null; image_task: string | null; video_task: string | null; status: string; error: string | null; retry_count?: number }
type Project = { id: string; title: string; status: string; message: string; output_directory?: string; parallelism?: number; deduplication?: { rewritten_scenes: number; history_scenes: number }; settings: { count: number; size: string; cameras: string[] }; scenes: Scene[] }
type Planning = { id: string; status: string; message: string; project_id: string | null }
type ProductionQueue = { processing?: number; waiting?: number; blocked?: number; running: boolean; total_prompts: number; items: { id: string; project_id: string; title: string; count: number; target: number; videos: number; blocked?: number; status: string; error?: string; quota_exhausted?: boolean }[] }
type QueuePrompt = { id: string; project_id: string; queue_id: string; ordinal: number; number: number; title: string; image_prompt: string; video_prompt: string; status: string; error: string | null; camera_label: string; video: string | null; retry_count?: number; quota_exhausted: boolean }
type PromptList = { items: QueuePrompt[]; page: number; pages: number; total: number; missing: string[] }
type Summary = { id: string; title: string; status: string }
const auth = { 'X-Flowkit-Local-Auth': '1' }
async function api<T>(path: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/muse/scenes${path}`, { headers: { ...auth, 'Content-Type': 'application/json' }, method: method || (body === undefined ? 'GET' : 'POST'), ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  if (!response.ok) {
    const result = await response.json().catch(() => ({}))
    throw new Error(typeof result.detail === 'string' ? result.detail : `Chưa thực hiện được yêu cầu (${response.status}).`)
  }
  return response.json()
}
const cameraDefaults: CameraOption[] = [
  { id: 'aerial', label: 'Fly cam' },
  { id: 'zoom_in', label: 'Zoom xa đến gần' },
  { id: 'static', label: 'Góc tĩnh' },
  { id: 'pan', label: 'Góc pan' },
  { id: 'zoom_out', label: 'Gần đến xa' },
  { id: 'close', label: 'Góc quay cận' },
]
const statusLabels: Record<string, string> = { needs_review: 'Cần đối chiếu tác vụ', draft: 'Sẵn sàng', running: 'Đang tạo', pending: 'Chờ tạo', image: 'Đang tạo ảnh', video: 'Đang tạo video', completed: 'Hoàn tất', image_ready: 'Ảnh đã sẵn sàng', error: 'Cần kiểm tra', paused: 'Đã tạm dừng' }
const control = 'landscape-input'
const btn = 'landscape-button'

function UpdateButton() {
  const [busy, setBusy] = useState(false)
  const run = async () => {
    const api = (window as unknown as { pywebview?: { api?: { check_update?: () => Promise<string> } } }).pywebview?.api
    if (!api?.check_update) { window.alert('Chức năng cập nhật chỉ có trong ứng dụng Muse Landscape Studio trên máy tính.'); return }
    setBusy(true)
    try { await api.check_update() } catch { window.alert('Không cập nhật được. Vui lòng thử lại.') }
    setBusy(false)
  }
  return <button className={btn} disabled={busy} onClick={run} title="Kiểm tra và cài bản cập nhật từ thư mục mạng LAN"><Download size={15} />{busy ? 'Đang kiểm tra…' : 'Cập nhật'}</button>
}

export default function LandscapeStudio() {
  const txtInput = useRef<HTMLInputElement>(null)
  const [cameras, setCameras] = useState(cameraDefaults)
  const [chosen, setChosen] = useState(['aerial', 'zoom_in', 'static'])
  const [cameraName, setCameraName] = useState('')
  const [cameraDescription, setCameraDescription] = useState('')
  const [topic, setTopic] = useState('')
  const [outputFolder, setOutputFolder] = useState('')
  const [folderInput, setFolderInput] = useState('')
  const [showDetails, setShowDetails] = useState(false)
  const [scenePage, setScenePage] = useState(0)
  const [autoRun, setAutoRun] = useState(true)
  const [count, setCount] = useState(6)
  const [size, setSize] = useState('16:9')
  const [style, setStyle] = useState('Phong cảnh chân thực, điện ảnh, màu sắc tự nhiên')
  const [lighting, setLighting] = useState('Bình minh, ánh nắng ấm và sương nhẹ')
  const [project, setProject] = useState<Project | null>(null)
  const [queueFilter, setQueueFilter] = useState('all')
  const [queuePage, setQueuePage] = useState(1)
  const [promptList, setPromptList] = useState<PromptList>({ items: [], page: 1, pages: 1, total: 0, missing: [] })
  const [previewVideo, setPreviewVideo] = useState('')
  const [queue, setQueue] = useState<ProductionQueue>({ running: false, total_prompts: 0, items: [] })
  const [saved, setSaved] = useState<Summary[]>([])
  const [operation, setBusy] = useState('')
  const [planning, setPlanning] = useState<Planning | null>(null)
  const [stopping, setStopping] = useState(false)
  const busy = operation || (planning?.status === 'running' ? 'Muse đang lập cảnh…' : '')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [dirty, setDirty] = useState(false)
  const [autoStarting, setAutoStarting] = useState(false)
  const [autoConnectionError, setAutoConnectionError] = useState('')
  const [quotaAccounts, setQuotaAccounts] = useState<string[]>([])
  const [savedAccountCount, setSavedAccountCount] = useState(0)
  const [connectionUncertain, setConnectionUncertain] = useState(false)
  const [performance, setPerformance] = useState<Performance>({ preset: 'balanced', max_accounts: 3, videos_per_account: 2, max_videos: 6, automatic: true })
  const [adaptive, setAdaptive] = useState<AdaptiveStatus | null>(null)
  const [activeAccountCount, setActiveAccountCount] = useState(0)
  const [availableAccounts, setAvailableAccounts] = useState(0)
  const [connected, setConnected] = useState(false)
  const [showConnection, setShowConnection] = useState(false)
  const running = project?.status === 'running'
  const refreshList = useCallback(() => api<Summary[]>('').then(setSaved), [])
  useEffect(() => {
    api<{ cameras: CameraOption[] }>('/options').then(result => { setCameras(result.cameras); setChosen(old => old.filter(id => result.cameras.some(camera => camera.id === id))) }).catch(() => {})
    api<{ directory: string }>('/storage').then(result => { setOutputFolder(result.directory); setFolderInput(result.directory) }).catch(() => {})
    refreshList().catch(() => {})
    const lastPlan = localStorage.getItem('muse-planning-job')
    if (lastPlan) api<Planning>('/planning/' + lastPlan).then(setPlanning).catch(() => localStorage.removeItem('muse-planning-job'))
    const stored = localStorage.getItem('muse-landscape-project')
    if (stored) api<Project>('/' + stored).then(setProject).catch(() => {})
    let statusPending = false
    const refresh = () => { if (statusPending) return; statusPending = true; return fetch(`${API_BASE_URL}/api/muse/status`, { headers: auth }).then(r => r.json()).then(s => { if (s.performance) setPerformance(s.performance); setAdaptive(s.scheduling?.adaptive || null); setConnectionUncertain(!!s.connection_uncertain); setSavedAccountCount(s.saved_accounts || 0); setConnected(s.ready); setActiveAccountCount(s.scheduling?.active_accounts || 0); setAvailableAccounts(s.ready ? s.available || 0 : 0); setQuotaAccounts(s.quota_accounts || []); setAutoStarting(!!s.auto_starting); setAutoConnectionError(s.auto_error || '') }).catch(() => { setConnected(false); setConnectionUncertain(true) }).finally(() => { statusPending = false }) }
    void refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [refreshList])
  useEffect(() => {
    if (!project?.id) return
    localStorage.setItem('muse-landscape-project', project.id)
    if (!running && !queue.running) return
    const timer = setInterval(() => {
      api<Project>('/' + project.id).then(value => { if (!dirty) setProject(value) }).catch(() => {})
    }, 2500)
    return () => clearInterval(timer)
  }, [project?.id, running, queue.running, dirty])
  useEffect(() => {
    const protect = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = '' } }
    window.addEventListener('beforeunload', protect)
    return () => window.removeEventListener('beforeunload', protect)
  }, [dirty])
  async function work(label: string, fn: () => Promise<void>) {
    setBusy(label); setError(''); setNotice('')
    try { await fn(); await refreshList() }
    catch (e) { setError(e instanceof Error ? e.message : 'Chưa xử lý được yêu cầu.') }
    finally { setBusy('') }
  }
  useEffect(() => {
    let pending = false, closed = false
    const refresh = async () => {
      if (pending || document.hidden) return
      pending = true
      try {
        const [state, list] = await Promise.all([api<ProductionQueue>('/queue'), api<PromptList>('/queue/prompts?page=' + queuePage + '&filter=' + queueFilter)])
        if (!closed) { setQueue(state); setPromptList(list) }
      } catch {} finally { pending = false }
    }
    void refresh()
    const timer = setInterval(refresh, 3000)
    return () => { closed = true; clearInterval(timer) }
  }, [queuePage, queueFilter])
  useEffect(() => { if (!showDetails) setScenePage(0) }, [project?.id, showDetails])
  async function saveFolder(directory: string) {
    const result = await api<{ directory: string; project: Project | null }>('/storage', { directory })
    setOutputFolder(result.directory); setFolderInput(result.directory)
    if (result.project) setProject(current => current ? { ...current, output_directory: result.project!.output_directory } : current)
    setNotice('Đã lưu thư mục đầu ra. Các lần tạo sau sẽ dùng thư mục này.')
  }
  async function saveEdits() {
    if (!project) throw new Error('Chưa có bộ cảnh.')
    const updated = await api<Project>('/' + project.id, { scenes: project.scenes.map(({ title, camera, image_prompt, video_prompt }) => ({ title, camera, image_prompt, video_prompt })) }, 'PUT')
    setProject(updated); setDirty(false)
    return updated
  }
  useEffect(() => {
    if (!planning || planning.status !== 'running') return
    let cancelled = false
    let loading = false
    const poll = async () => {
      if (loading) return
      loading = true
      try {
        const job = await api<Planning>('/planning/' + planning.id)
        if (cancelled) return
        if (job.status === 'running' && job.project_id) setProject(await api<Project>('/' + job.project_id))
        if (job.status === 'completed' && job.project_id) {
          const result = await api<Project>('/' + job.project_id)
          if (cancelled) return
          setProject(result); setDirty(false); setNotice(job.message); await refreshList()
        } else if (job.status === 'error' || job.status === 'stopped') {
          if (job.project_id) setProject(await api<Project>('/' + job.project_id))
          if (job.status === 'error') setError(job.message); else setNotice(job.message)
        }
        else if (job.status === 'stopped') setNotice(job.message)
        setPlanning(job)
        if (job.status !== 'running') localStorage.removeItem('muse-planning-job')
      } catch { if (!cancelled) setNotice('Đang kiểm tra tiến độ lập cảnh…') }
      finally { loading = false }
    }
    void poll()
    const timer = setInterval(poll, 1500)
    return () => { cancelled = true; clearInterval(timer) }
  }, [planning?.id, planning?.status, refreshList])
  async function importTxt(file: File) {
    await work('Đang nhập prompt TXT…', async () => {
      if (!file.name.toLowerCase().endsWith('.txt')) throw new Error('Hãy chọn file .txt.')
      if (file.size > 10_000_000) throw new Error('File TXT tối đa 10 MB.')
      const bytes = new Uint8Array(await file.arrayBuffer())
      let text: string
      try {
        const encoding = bytes[0] === 0xff && bytes[1] === 0xfe ? 'utf-16le' : bytes[0] === 0xfe && bytes[1] === 0xff ? 'utf-16be' : 'utf-8'
        text = new TextDecoder(encoding, { fatal: true }).decode(bytes)
      } catch { throw new Error('Không đọc được chữ trong file. Hãy lưu TXT dưới dạng UTF-8 hoặc UTF-16.') }
      const result = await api<{ queue: ProductionQueue; imported: number }>('/queue/import-txt', { text, filename: file.name, size })
      setQueue(result.queue); setQueueFilter('all'); setQueuePage(1)
      setPromptList(await api<PromptList>('/queue/prompts'))
      setNotice(`Đã thêm ${result.imported} prompt từ ${file.name}. ${result.queue.running ? 'Hàng đợi đang tiếp tục xử lý.' : 'Bấm Chạy hàng đợi khi sẵn sàng.'}`)
      await refreshList()
    })
  }
  async function stopNow() {
    setStopping(true)
    try {
      if (planning?.status === 'running') {
        const result = await api<Planning>('/planning/' + planning.id + '/stop', {})
        setPlanning(result); setNotice(result.message); localStorage.removeItem('muse-planning-job'); if (result.project_id) { setProject(await api<Project>('/' + result.project_id)); setDirty(false); await refreshList() }
      } else if (project && running) setProject(await api<Project>('/' + project.id + '/stop', {}))
    } catch (e) { setError(e instanceof Error ? e.message : 'Chưa dừng được; thử lại.') }
    finally { setStopping(false) }
  }
  const change = (index: number, key: keyof Scene, value: string) => {
    setProject(old => old && ({ ...old, scenes: old.scenes.map((s, i) => i === index ? { ...s, [key]: value } : s) })); setDirty(true)
  }
  return <div className="landscape-app">
    <header className="landscape-header"><div className="flex items-center gap-3"><img className="landscape-logo" src="/app-icon.png" alt="" /><div><div className="font-semibold tracking-tight text-lg">Muse Landscape Studio</div><div className="text-xs text-slate-400">Muse · Text to Video</div></div></div>
      <div className="flex items-center gap-2"><UpdateButton />
      <button className={btn} onClick={() => setShowConnection(!showConnection)}><span className={'h-2 w-2 rounded-full ' + (connected ? 'bg-emerald-400' : 'bg-amber-400')} />{autoStarting ? 'Đang kết nối Muse…' : connectionUncertain ? `Đang kiểm tra Muse · ${savedAccountCount} tài khoản đã lưu` : `Muse ${connected ? 'đã kết nối' : 'chưa sẵn sàng'} · ${activeAccountCount}/${performance.max_accounts} đang dùng · ${availableAccounts} khả dụng`}<Settings2 size={15} /></button></div></header>
    <main className="max-w-[1600px] mx-auto px-5 md:px-8 py-6 space-y-5">
      {showConnection && <div className="landscape-panel"><div className="flex justify-between mb-4"><h2 className="font-semibold">Tài khoản Muse</h2><button className={btn} onClick={() => setShowConnection(false)}>Thu gọn</button></div><MusePage connectionOnly /></div>}
      <div className="flex flex-wrap justify-between items-end gap-4"><div><div className="text-[10px] uppercase tracking-[.2em] text-emerald-400 mb-2">Phong cảnh · Không có người</div><h1 className="text-2xl font-semibold tracking-tight">Tạo video phong cảnh</h1><p className="text-slate-400 text-sm mt-3">Viết bối cảnh · chọn camera · theo dõi hàng đợi</p></div>
        <select className={control + ' max-w-72'} value={project?.id || ''} disabled={!!busy || running} onChange={e => { if (!e.target.value) return; if (dirty && !confirm('Bạn có thay đổi chưa lưu. Mở bộ cảnh khác và bỏ thay đổi?')) return; work('Đang mở…', async () => { setProject(await api<Project>('/' + e.target.value)); setDirty(false); setShowDetails(true) }) }}><option value="">Bộ cảnh đã lưu</option>{saved.map(item => <option key={item.id} value={item.id}>{item.title} · {statusLabels[item.status]}</option>)}</select></div>
      {autoConnectionError && !connected && <div role="alert" className="landscape-alert border-red-500/40 text-red-200">{autoConnectionError} <button className="underline ml-2" onClick={() => setShowConnection(true)}>Mở tài khoản Muse</button></div>}
      {error && <div role="alert" className="landscape-alert border-red-500/40 text-red-200">{error}</div>}{notice && <div role="status" className="landscape-alert">{notice}</div>}{busy && <div role="status" className="flex items-center gap-2 text-sm text-emerald-300"><LoaderCircle size={16} className="animate-spin" />{busy}</div>}
      {planning?.status === 'running' && <div className="landscape-alert flex items-center justify-between gap-4"><div className="text-sm">{planning?.status === 'running' ? planning.message : project?.message}<p className="text-xs opacity-60 mt-1">Dừng sẽ giữ tiến độ và ngừng gửi yêu cầu mới. Tác vụ đã gửi Muse có thể vẫn chạy.</p></div><button className={btn} disabled={stopping} onClick={stopNow}><Pause size={15} />{stopping ? 'Đang dừng…' : 'Dừng lập prompt'}</button></div>}

      <AdaptiveStatusPanel status={adaptive} enabled={performance.automatic} ceiling={performance.max_videos} /><div className="production-stats"><div><span>Đang chờ</span><strong>{(queue.waiting ?? 0).toLocaleString('vi-VN')}</strong></div><div><span>Prompt đã nhận</span><strong>{queue.total_prompts.toLocaleString('vi-VN')}</strong></div><div><span>Video hoàn thành</span><strong>{queue.items.reduce((sum, row) => sum + row.videos, 0).toLocaleString('vi-VN')}</strong></div><div><span>Đang xử lý</span><strong>{queue.processing || 0}</strong></div><div><span>Cảnh lỗi / cần đối chiếu</span><strong className="text-amber-200">{queue.blocked || 0}</strong></div><div><span>Trạng thái</span><strong className={queue.running ? 'is-active' : ''}>{queue.running ? 'Đang chạy' : planning?.status === 'running' ? 'Đang viết prompt' : queue.items.some(row => row.quota_exhausted) ? 'Hết hạn mức' : queue.items.some(row => row.status === 'error') ? 'Cần kiểm tra' : 'Sẵn sàng'}</strong></div></div>
      <div className="landscape-workspace">
        <aside className="landscape-panel landscape-design space-y-5">
          <PerformanceSettingsPanel value={performance} disabled={!!busy || queue.running || !!running} onChange={(preset, automatic) => { work('Đang lưu hiệu năng…', async () => { const response = await fetch(`${API_BASE_URL}/api/muse/performance`, { method: 'POST', headers: { ...auth, 'Content-Type': 'application/json' }, body: JSON.stringify({ preset, automatic }) }); const value = await response.json(); if (!response.ok) throw new Error(value.detail || 'Chưa đổi được hiệu năng'); setPerformance(value) }) }} />
          <div className="flex items-center gap-2 font-semibold"><span className="landscape-step">1</span> Nội dung</div>
          <label className="landscape-label">Mô tả bối cảnh<textarea className={control + ' min-h-28 mt-2'} value={topic} maxLength={3000} disabled={!!busy} onChange={e => setTopic(e.target.value)} placeholder="Viết mô tả của bạn tại đây khi sẵn sàng…" /></label>
          <div className="grid grid-cols-2 gap-3"><label className="landscape-label">Số prompt<input className={control + ' mt-2'} type="number" min={1} max={9999} value={count} disabled={!!busy} onChange={e => setCount(Number(e.target.value))} /><span className="text-[11px] text-slate-500 font-normal mt-1 block">1–9.999 cảnh · thời lượng thực tế theo Muse</span></label><label className="landscape-label">Tỉ lệ khung hình<select className={control + ' mt-2'} value={size} disabled={!!busy} onChange={e => setSize(e.target.value)}><option>16:9</option><option>9:16</option><option>1:1</option></select></label></div>
          <details className="landscape-advanced"><summary><Settings2 size={14} /> Phong cách & ánh sáng <span className="ml-auto text-xs opacity-60">Tùy chọn</span></summary><div className="space-y-4 mt-4">          <label className="landscape-label">Phong cách<input className={control + ' mt-2'} value={style} maxLength={500} disabled={!!busy} onChange={e => setStyle(e.target.value)} /></label>
          <label className="landscape-label">Ánh sáng / thời điểm<input className={control + ' mt-2'} value={lighting} maxLength={300} disabled={!!busy} onChange={e => setLighting(e.target.value)} /></label>
</div></details>
          <div className="landscape-divider" />
          <div className="flex items-center gap-2 font-semibold"><span className="landscape-step">2</span> Góc camera</div>
          <div><div className="landscape-label flex gap-2 items-center"><Camera size={15} />Chọn các góc bạn muốn</div><p className="text-xs text-slate-400 mt-2 mb-3">Chọn nhiều góc; mỗi cảnh lấy ngẫu nhiên một góc đã chọn.</p><div className="grid grid-cols-2 gap-2">{cameras.map(camera => <label key={camera.id} className={'landscape-camera ' + (chosen.includes(camera.id) ? 'selected' : '')}><input type="checkbox" checked={chosen.includes(camera.id)} disabled={!!busy} onChange={e => setChosen(old => e.target.checked ? [...old, camera.id] : old.filter(id => id !== camera.id))} /><span>{camera.label}</span></label>)}</div><div className="text-xs text-slate-500 mt-2">Đã chọn {chosen.length} góc · có thể lặp góc giữa các cảnh</div><button className={btn + ' mt-3 text-red-300'} disabled={!!busy || !chosen.length} onClick={() => { if (!confirm('Xóa ' + chosen.length + ' góc camera đang tích khỏi danh sách? Bộ cảnh đã lưu vẫn giữ camera cũ.')) return; work('Đang xóa camera…', async () => { const result = await api<{ cameras: CameraOption[] }>('/cameras/delete', { ids: chosen }); setCameras(result.cameras); setChosen([]); setNotice('Đã xóa các góc đã tích. Chọn hoặc thêm góc mới trước khi lập cảnh.') }) }}>Xóa góc đã tích ({chosen.length})</button></div>
          <details className="landscape-advanced"><summary className="text-sm cursor-pointer text-emerald-300">+ Thêm góc camera riêng</summary><div className="space-y-3 mt-3"><label className="landscape-label text-xs">Tên góc camera<input className={control + ' mt-2'} value={cameraName} maxLength={100} disabled={!!busy} onChange={e => setCameraName(e.target.value)} placeholder="Ví dụ: Sát mặt nước" /></label><label className="landscape-label text-xs">Mô tả góc nhìn / chuyển động<textarea className={control + ' mt-2 min-h-20'} value={cameraDescription} maxLength={1000} disabled={!!busy} onChange={e => setCameraDescription(e.target.value)} placeholder="Máy sát mặt nước, nhìn về phía chân trời; tiến chậm về phía trước." /></label><button className={btn + ' w-full'} disabled={!!busy || cameraName.trim().length < 2 || cameraDescription.trim().length < 5} onClick={() => work('Đang thêm camera…', async () => { const camera = await api<CameraOption>('/cameras', { label: cameraName.trim(), description: cameraDescription.trim() }); setCameras(old => [...old, camera]); setChosen(old => [...old, camera.id]); setCameraName(''); setCameraDescription(''); setNotice('Đã thêm và chọn góc camera mới. Góc này được lưu cho những lần sau.') })}>Thêm & chọn góc này</button><p className="text-[11px] text-slate-500">Nhập tiếng Việt hoặc tiếng Anh. Mô tả này được đưa vào prompt tạo ảnh và video.</p></div></details>
          <section className="landscape-output"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-sm font-medium">Thư mục đầu ra</h3></div><button className={btn} disabled={!!busy || !outputFolder} onClick={() => work('Đang mở thư mục…', async () => { await api('/storage/open', {}) })}>Mở</button></div><div className="mt-3 flex flex-wrap gap-2"><input aria-label="Thư mục đầu ra" className={control + ' flex-1 min-w-48'} value={folderInput} onChange={e => setFolderInput(e.target.value)} placeholder="D:\video" disabled={!!busy || running} /><button className={btn} disabled={!!busy || running} onClick={() => work('Đang chọn thư mục…', async () => { const result = await api<{ directory: string | null }>('/storage/choose', {}); if (result.directory) await saveFolder(result.directory) })}>Chọn thư mục…</button><button className={btn} disabled={!!busy || running || !folderInput.trim()} onClick={() => work('Đang lưu thư mục…', () => saveFolder(folderInput))}>Lưu thư mục</button></div></section>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={autoRun} disabled={!!busy} onChange={e => setAutoRun(e.target.checked)} />Tự khởi động video khi có prompt</label>
          <button className={btn + ' primary w-full'} disabled={!!busy || !connected || !chosen.length || !topic.trim() || !style.trim() || !lighting.trim() || count < 1 || count > 9999 || !Number.isInteger(count)} onClick={() => { if (dirty && !confirm('Bỏ thay đổi chưa lưu để lập bộ cảnh mới?')) return; work('Muse đang viết prompt cho từng cảnh…', async () => { const job = await api<Planning>('/plan/start?enqueue=true&auto_run=' + autoRun, { topic, count, cameras: chosen, size, style, lighting }); setPlanning(job); localStorage.setItem('muse-planning-job', job.id) }) }}><Aperture size={17} />Thêm {count || ''} prompt</button>
          {!connected && <button className="text-sm text-emerald-400 underline" onClick={() => setShowConnection(true)}>Kết nối tài khoản Muse để bắt đầu</button>}
          <p className="landscape-hint">Tắt tự khởi động để tích lũy trước khi chạy.</p>
        </aside>
        <div className="production-main space-y-4 min-w-0">
      <section className="landscape-panel production-queue space-y-3">{quotaAccounts.length > 0 && <p role="alert" className="landscape-alert text-amber-200">Hết hạn mức: {quotaAccounts.join(', ')}. {autoStarting || connectionUncertain ? 'Đang kiểm tra kết nối; chưa xác nhận được các tài khoản còn khả dụng.' : connected ? 'Đã ngừng giao việc cho các tài khoản này; dùng tài khoản còn khả dụng.' : 'Không còn tài khoản khả dụng. Thêm tài khoản hoặc chờ hạn mức phục hồi.'}</p>}<div className="queue-toolbar flex flex-wrap justify-between items-center gap-3"><div><h2 className="font-semibold">Hàng đợi sản xuất</h2><p className="landscape-hint mt-1">{queue.running ? 'Đang xử lý · prompt mới sẽ tự nhập vào hàng đợi' : 'Mỗi dòng là một prompt · prompt mới xuất hiện khi hoàn thành'}</p></div><div className="flex flex-wrap gap-2"><input ref={txtInput} type="file" accept=".txt,text/plain" aria-label="Chọn file prompt TXT" className="hidden" onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void importTxt(file) }} /><button className={btn} disabled={!!operation} title="Mỗi dòng không trống là một prompt. Giữ nguyên nội dung, không viết lại bằng AI." onClick={() => txtInput.current?.click()}>Nhập TXT</button>{!queue.running && queue.items.some(row => (row.blocked || 0) > 0) && <button className={btn + ' primary'} disabled={!!busy || queue.running || running || !connected} onClick={() => { const count = queue.items.reduce((sum, row) => sum + (row.blocked || 0), 0); if (!confirm(`Gửi lại ${count} cảnh lỗi? Giữ nguyên prompt và video hoàn thành. Yêu cầu cũ chưa rõ trạng thái có thể tạo video trùng và dùng thêm hạn mức. Bạn đồng ý gửi lại?`)) return; work('Đang khôi phục và chạy các cảnh lỗi…', async () => { setQueue(await api<ProductionQueue>('/queue/requeue-failed', { confirm_resubmit: true })); setPromptList(await api<PromptList>('/queue/prompts?page=' + queuePage + '&filter=' + queueFilter)); setQueue(await api<ProductionQueue>('/queue/start', {})); setProject(null); setDirty(false) }) }}>Gửi lại {queue.items.reduce((sum, row) => sum + (row.blocked || 0), 0)} cảnh lỗi</button>}<button className={btn} disabled={!!busy || queue.running || running || !queue.items.length} onClick={() => { if (!confirm('Dọn toàn bộ prompt khỏi hàng đợi? Video đã lưu và dữ liệu cũ vẫn được giữ.')) return; work('Đang dọn prompt…', async () => { setQueue(await api<ProductionQueue>('/queue/clear', {})); setPromptList(await api<PromptList>('/queue/prompts')); setQueuePage(1); setShowDetails(false); setProject(null); setDirty(false) }) }}>Dọn prompt</button><button className={btn + ' primary'} disabled={!!operation || queue.running || running || !connected || !queue.items.some(row => row.status !== 'completed')} onClick={() => work('Đang chạy hàng đợi…', async () => { if (dirty) await saveEdits(); setQueue(await api<ProductionQueue>('/queue/start', {})) })}><Play size={15} />Chạy hàng đợi</button>{queue.running && <button className={btn} disabled={!!operation} onClick={() => work('Đang dừng hàng đợi…', async () => { setQueue(await api<ProductionQueue>('/queue/stop', {})); if (project) setProject(await api<Project>('/' + project.id)) })}>Dừng hàng đợi</button>}</div></div>{!queue.items.length && <p className="text-sm text-slate-400">Chưa có prompt. Nhập bối cảnh bên trái hoặc chọn Nhập TXT · mỗi dòng là một prompt.</p>}{promptList.missing.length > 0 && <div className="landscape-hint text-amber-200">{promptList.missing.length} mục cũ không còn dữ liệu prompt. {promptList.missing.map(id => <button key={id} className={btn} disabled={queue.running} onClick={() => work('Đang dọn mục cũ…', async () => { setQueue(await api<ProductionQueue>('/queue/' + id + '/remove', {})) })}>Bỏ mục trống</button>)}</div>}
{queue.items.filter(row => row.count > 0 && row.count < row.target).map(row => <div key={row.id} className="landscape-hint flex items-center justify-between gap-3"><span>Đã nhận {row.count}/{row.target} prompt · {planning?.status === 'running' ? 'Đang viết tiếp' : 'Còn phần chưa viết'}</span><button className={btn} disabled={!!busy || queue.running || !connected} onClick={() => work('Đang tiếp tục lập prompt…', async () => { const job = await api<Planning>('/' + row.project_id + '/plan/resume', {}); setPlanning(job); localStorage.setItem('muse-planning-job', job.id) })}>Tiếp tục lập</button></div>)}
<div className="queue-progress-summary" role="status"><span>{queue.items.reduce((sum, row) => sum + row.videos, 0).toLocaleString('vi-VN')} / {queue.total_prompts.toLocaleString('vi-VN')} video hoàn thành</span><progress aria-label="Tiến độ tạo video" max={Math.max(1, queue.total_prompts)} value={queue.items.reduce((sum, row) => sum + row.videos, 0)} /></div><div className="queue-filter-bar"><div className="flex flex-wrap gap-2">{[['all', 'Tất cả'], ['waiting', 'Đang chờ'], ['processing', 'Đang xử lý'], ['error', 'Cảnh lỗi'], ['completed', 'Hoàn thành']].map(([value, label]) => <button key={value} className={btn + (queueFilter === value ? ' selected-filter' : '')} aria-pressed={queueFilter === value} onClick={() => { setQueueFilter(value); setQueuePage(1) }}>{label}</button>)}</div><p className="landscape-hint">Tối đa {performance.max_accounts} tài khoản · {performance.videos_per_account} video/tài khoản · Giữ video đã hoàn thành</p></div>{!promptList.items.length && queue.items.length > 0 && <p className="landscape-hint py-4">Không có prompt thuộc trạng thái này.</p>}{promptList.items.map(row => <article key={row.id} className="prompt-queue-row"><div className="flex items-start gap-3"><span className="production-index">{String(row.ordinal).padStart(3, '0')}</span><div className="flex-1 min-w-0"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="production-row-title">{row.title}</h3><span className="landscape-badge">{row.quota_exhausted ? 'Hết hạn mức' : statusLabels[row.status] || row.status}</span></div><p className="landscape-hint mt-1">{row.camera_label}{row.retry_count ? ` · Thử lại ${row.retry_count}/5` : ''}</p></div></div><p className="prompt-queue-text">{row.image_prompt}</p><details className="prompt-motion"><summary>Chuyển động</summary><p className="landscape-hint mt-2">{row.video_prompt}</p></details>{(row.error || row.quota_exhausted) && <p role="alert" className={row.quota_exhausted ? 'landscape-alert border-red-400/50 text-red-200 text-sm' : 'text-red-300 text-xs'}>{row.quota_exhausted ? 'Tài khoản Muse hết hạn mức — đã dừng hàng đợi.' : row.error}</p>}<div className="flex flex-wrap gap-2 mt-3">{row.video && !queue.running && <button className={btn} onClick={() => setPreviewVideo(old => old === row.id ? '' : row.id)}>{previewVideo === row.id ? 'Ẩn video' : 'Xem video'}</button>}<button className={btn} disabled={!!operation} onClick={() => work('Đang mở thư mục…', async () => { await api('/storage/open?project=' + row.project_id, {}) })}>Mở thư mục</button><button className={btn} disabled={!!operation} onClick={() => { if (dirty && !confirm('Bỏ thay đổi chưa lưu?')) return; work('Đang mở prompt…', async () => { const value = await api<Project>('/' + row.project_id); setProject(value); setScenePage(Math.floor(value.scenes.findIndex(scene => scene.id === row.id) / 20)); setDirty(false); setShowDetails(true) }) }}>Chi tiết prompt</button></div>{previewVideo === row.id && row.video && !queue.running && <div className="mt-3"><Media name={row.video} kind="video" /></div>}</article>)}
{promptList.total > 0 && <div className="prompt-queue-pagination"><button className={btn} disabled={promptList.page <= 1} onClick={() => setQueuePage(promptList.page - 1)}>Trang trước</button><span>{promptList.total.toLocaleString('vi-VN')} prompt · Trang {promptList.page}/{promptList.pages}</span><button className={btn} disabled={promptList.page >= promptList.pages} onClick={() => setQueuePage(promptList.page + 1)}>Trang sau</button></div>}
</section>

          {showDetails && project && <div className="flex justify-between items-center"><h3 className="font-semibold">Chi tiết prompt và kết quả</h3><button className={btn} onClick={() => setShowDetails(false)}>Thu gọn</button>{dirty && <button className={btn} disabled={!!busy || running} onClick={() => work('Đang lưu…', async () => { await saveEdits() })}>Lưu chỉnh sửa</button>}</div>}
          {showDetails && project && <div className="flex items-center gap-3"><button className={btn} disabled={scenePage === 0} onClick={() => setScenePage(p => p - 1)}>Trang trước</button><span className="text-sm">Trang {scenePage + 1}/{Math.max(1, Math.ceil(project.scenes.length / 20))} · {project.scenes.length}/{project.settings.count} cảnh</span><button className={btn} disabled={(scenePage + 1) * 20 >= project.scenes.length} onClick={() => setScenePage(p => p + 1)}>Trang sau</button></div>}{showDetails && project?.scenes.slice(scenePage * 20, (scenePage + 1) * 20).map((scene, pageIndex) => { const index = scenePage * 20 + pageIndex; const locked = running || !!scene.image_task || !!scene.video_task; return <article className="landscape-panel" key={scene.id}>
            <div className="flex justify-between gap-3 items-center mb-4"><div className="flex gap-3 items-center"><span className="text-emerald-400 text-xs font-mono">{String(scene.number).padStart(2, '0')}</span><input aria-label={`Tên cảnh ${scene.number}`} className="bg-transparent font-medium min-w-0 w-full outline-none" value={scene.title} disabled={locked || !!busy} onChange={e => change(index, 'title', e.target.value)} /></div><span className="landscape-badge shrink-0">{statusLabels[scene.status] || scene.status}</span></div>
            <div className="grid md:grid-cols-[minmax(0,1fr)_220px] gap-4"><div className="space-y-3"><label className="landscape-label text-xs">Mô tả cảnh<textarea className={control + ' mt-2 min-h-24'} value={scene.image_prompt} disabled={locked || !!busy} onChange={e => change(index, 'image_prompt', e.target.value)} /></label><details><summary className="text-xs text-slate-400 cursor-pointer flex gap-1 items-center"><ChevronDown size={13} />Prompt chuyển động</summary><textarea aria-label={`Prompt video cảnh ${scene.number}`} className={control + ' mt-2 min-h-20'} value={scene.video_prompt} disabled={locked || !!busy} onChange={e => change(index, 'video_prompt', e.target.value)} /></details></div>
              <div><label className="landscape-label text-xs">Camera cảnh này<select className={control + ' mt-2'} value={scene.camera} disabled={locked || !!busy} onChange={e => change(index, 'camera', e.target.value)}>{!cameras.some(camera => camera.id === scene.camera) && <option value={scene.camera}>Góc đã lưu của cảnh</option>}{cameras.map(camera => <option key={camera.id} value={camera.id}>{camera.label}</option>)}</select></label><p className="text-[11px] text-slate-500 mt-3">{locked ? 'Giữ nguyên camera cho tác vụ đã gửi.' : 'Được chọn từ các góc bạn cho phép. Bạn có thể đổi trước khi chạy.'}</p><div className="mt-4 flex gap-2 text-xs text-slate-400"><Film size={14} />Khoảng 8 giây · không có người</div></div></div>
            {scene.error && <div role="alert" className="text-red-300 text-sm mt-4">{scene.retry_count ? `Đã thử lại ${scene.retry_count}/5 lần. ` : ''}{scene.error}</div>}
            {(scene.image || scene.video) && <div className="grid md:grid-cols-2 gap-5 mt-5 pt-5 border-t border-slate-800">{scene.image && <Media name={scene.image} kind="image" />}{scene.video && <Media name={scene.video} kind="video" />}</div>}
          </article> })}
        </div>
      </div>
    </main>
  </div>
}







