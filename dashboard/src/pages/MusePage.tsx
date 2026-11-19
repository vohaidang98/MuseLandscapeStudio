import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_URL, fetchAPI } from '../api/client'

type Status = { performance?: { max_accounts: number; videos_per_account: number; max_videos: number }; scheduling?: { active_accounts: number }; connection_uncertain?: boolean; saved_accounts?: number; auto_starting?: boolean; auto_error?: string; running: boolean; ready: boolean; available: number; driver: string | null; chrome_installed: boolean }
type TokenRefresh = { running: boolean; completed: number; total: number }
type AdditionalTokens = { remaining_label?: string; checked_at?: number; attempted_at?: number; error?: string | null }
type Account = { id: string; label: string; enabled: boolean; status: string; work_role?: string; quota_exhausted?: boolean; additional_tokens?: AdditionalTokens | null; token_loading?: boolean }
type Job = { id: string; kind: 'image' | 'video'; prompt: string; status?: string; progress?: number; media?: string[]; error?: string }
const names = ['hatch_sess', 'hatch_gw', 'hatch_vml', 'hatch_native_auth_device']
const requiredNames = names.filter(name => name !== 'hatch_gw')
const headers = { 'X-Flowkit-Local-Auth': '1' }
const call = <T,>(path: string, body?: unknown) => fetchAPI<T>('/api/muse' + path,
  { headers, ...(body !== undefined ? { method: 'POST', body: JSON.stringify(body) } : {}) })
const field = 'w-full rounded-lg border p-3 bg-transparent text-sm'
const button = 'rounded-lg border px-4 py-2 text-sm hover:opacity-80 disabled:opacity-40'

export function Media({ name, kind }: { name: string; kind: 'image' | 'video' }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState(false)
  useEffect(() => {
    let active = true
    let object = ''
    fetch(`${API_BASE_URL}/api/muse/media/${encodeURIComponent(name)}`, { headers })
      .then(r => { if (!r.ok) throw new Error(); return r.blob() })
      .then(blob => { if (active) { object = URL.createObjectURL(blob); setUrl(object) } })
      .catch(() => { if (active) setError(true) })
    return () => { active = false; if (object) URL.revokeObjectURL(object) }
  }, [name])
  if (error) return <p>Không mở được kết quả; kiểm tra thư mục dữ liệu Muse.</p>
  if (!url) return <p>Đang tải kết quả…</p>
  return <div className="space-y-2">
    {kind === 'image' ? <img src={url} alt="Ảnh được tạo bằng Muse" className="max-h-80 rounded-lg" /> : <video src={url} controls className="max-h-80 rounded-lg" />}
    <a href={url} download={name} className="underline text-sm">Lưu {kind === 'image' ? 'ảnh' : 'video'} về máy</a>
  </div>
}

export default function MusePage({ connectionOnly = false }: { connectionOnly?: boolean }) {
  const [status, setStatus] = useState<Status | null>(null)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [accounts, setAccounts] = useState<Account[]>([])
  const [tokenRefresh, setTokenRefresh] = useState<TokenRefresh>({ running: false, completed: 0, total: 0 })
  const tokensRequested = useRef('')
  const [accountName, setAccountName] = useState('FrameWeaver')
  const [consent, setConsent] = useState(false)
  const [cookies, setCookies] = useState<Record<string, string>>({})
  const [mode, setMode] = useState<'chat' | 'image' | 'video'>('chat')
  const [prompt, setPrompt] = useState('')
  const [size, setSize] = useState('16:9')
  const [references, setReferences] = useState<string[]>([])
  const [answer, setAnswer] = useState('')
  const [jobs, setJobs] = useState<Job[]>([])
  const jobsRef = useRef(jobs)
  const refreshing = useRef(false)
  const refresh = useCallback(async () => {
    if (refreshing.current) return
    refreshing.current = true
    try {
      await Promise.allSettled([
        call<Status>('/status').then(setStatus),
        call<Account[]>('/accounts').then(setAccounts),
        call<TokenRefresh>('/accounts/tokens/status').then(setTokenRefresh),
      ])
    } finally { refreshing.current = false }
  }, [])
  useEffect(() => {
    if (!status?.running || tokenRefresh.running || (status.scheduling?.active_accounts || 0) > 0) return
    const expired = accounts.filter(account => account.quota_exhausted && Date.now() / 1000 - Math.max(account.additional_tokens?.checked_at || 0, account.additional_tokens?.attempted_at || 0) > 900)
    const key = expired.map(account => account.id).sort().join(',')
    if (!key || tokensRequested.current === key) return
    tokensRequested.current = key
    call<TokenRefresh>('/accounts/tokens/refresh', {}).then(setTokenRefresh).catch(() => {})
  }, [status?.running, status?.scheduling?.active_accounts, accounts, tokenRefresh.running])
  useEffect(() => { jobsRef.current = jobs }, [jobs])
  useEffect(() => {
    refresh().catch(() => {})
    call<Job[]>('/tasks').then(setJobs).catch(() => {})
    const timer = setInterval(() => { refresh().catch(() => {}) }, 6000)
    return () => clearInterval(timer)
  }, [refresh])
  useEffect(() => {
    if (!status?.running) return
    let stopped = false
    let polling = false
    const poll = async () => {
      if (polling) return
      polling = true
      try {
        for (const job of jobsRef.current.slice(0, 30)) {
          if (['succeeded', 'failed', 'cancelled', 'unavailable'].includes(job.status || '')) continue
          try {
            const result = await call<Partial<Job>>('/tasks/' + job.id)
            if (!stopped) setJobs(old => old.map(item => item.id === job.id ? { ...item, ...result } : item))
          } catch {
            if (!stopped) setJobs(old => old.map(item => item.id === job.id ? { ...item, status: 'unavailable', error: 'Chưa đọc được tác vụ. Bấm Nạp lại lịch sử sau khi kết nối gateway.' } : item))
          }
        }
      } finally { polling = false }
    }
    const timer = setInterval(poll, 3000)
    void poll()
    return () => { stopped = true; clearInterval(timer) }
  }, [status?.running])
  async function run(label: string, work: () => Promise<void>) {
    setBusy(label); setError(''); setNotice('')
    try { await work(); await refresh() }
    catch (e) {
      let message = e instanceof Error ? e.message : 'Chưa thực hiện được thao tác.'
      try { const parsed = JSON.parse(message.slice(message.indexOf('{'))); if (typeof parsed.detail === 'string') message = parsed.detail } catch { /* Plain messages are already readable. */ }
      setError(message)
    }
    finally { setBusy('') }
  }
  async function selectFiles(files: FileList | null) {
    setReferences([]); setError('')
    if (!files) return
    if (files.length > 4 || Array.from(files).some(f => !['image/png', 'image/jpeg', 'image/webp'].includes(f.type) || f.size > 9 * 1024 * 1024)) {
      setError('Chọn tối đa 4 ảnh PNG/JPEG/WebP, mỗi ảnh dưới 9 MB.'); return
    }
    setReferences(await Promise.all(Array.from(files).map(file => new Promise<string>((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file)
    }))))
  }
  async function submit() {
    await run('Đang gửi Muse…', async () => {
      if (mode === 'chat') {
        const result = await call<{ text: string }>('/chat', { prompt })
        setAnswer(result.text); setNotice('Muse đã trả lời yêu cầu thật. Quyền tạo ảnh/video vẫn phụ thuộc tài khoản.')
      } else {
        const result = await call<{ id: string; status: string }>('/generate', { kind: mode, prompt, size, references })
        setJobs(old => [{ id: result.id, status: result.status, prompt, kind: mode }, ...old])
        setNotice('Đã gửi một yêu cầu. Đợi kết quả trong lịch sử, tránh gửi lại khi chưa rõ trạng thái.')
      }
    })
  }
  return <div className="max-w-5xl mx-auto space-y-6">
    {!connectionOnly && <div><h1 className="text-2xl font-semibold">Muse AI</h1><p className="text-sm opacity-70 mt-2">Kết nối tài khoản Muse của bạn, tạo nội dung, ảnh và video từ ảnh ngay trong FrameWeaver.</p></div>}
    <section className="rounded-xl border p-5 space-y-4">
      <h2 className="font-semibold">1. Kết nối Muse</h2>
      <p className="text-sm">{status?.connection_uncertain ? 'Gateway phản hồi chậm; đang kiểm tra lại. Tài khoản đã lưu vẫn được giữ.' : status?.running ? `Gateway đang chạy · ${status.driver} · ${status.available} phiên khả dụng` : 'Gateway chưa chạy hoặc chưa kết nối được.'} {status?.ready && 'Phiên đã lưu; hãy gửi câu thử để xác minh đăng nhập.'}</p>
      {status && !status.running && !status.chrome_installed && <p className="text-sm text-amber-500">Cài Google Chrome trước khi khởi động Muse.</p>}
      <div className="flex gap-2 flex-wrap">
        <button className={button} disabled={!!busy} onClick={() => run('Đang khởi động gateway…', async () => { await call('/start', {}) })}>Khởi động Muse</button>
        <button className={button} disabled={!!busy || !status?.running} onClick={() => run('Đang dừng gateway…', async () => { await call('/stop', {}) })}>Dừng gateway của ứng dụng</button>
        <button className={button} disabled={!!busy} onClick={() => run('Đang kiểm tra…', async () => { await refresh() })}>Kiểm tra kết nối</button>
      </div>
      <div className="space-y-3 rounded-xl border border-slate-700 p-4"><div className="flex flex-wrap justify-between items-center gap-3"><h3 className="font-medium">Tài khoản Muse · {accounts.length} đã lưu · Tối đa {status?.performance?.max_accounts || 3} tài khoản hoạt động</h3><button className={button} disabled={!!busy || tokenRefresh.running || !accounts.some(account => account.quota_exhausted)} onClick={() => run('Đang kiểm tra token bổ sung…', async () => { setTokenRefresh(await call<TokenRefresh>('/accounts/tokens/refresh', {})) })}>{tokenRefresh.running ? `Đang đọc token ${tokenRefresh.completed}/${tokenRefresh.total}` : 'Kiểm tra token TK giới hạn'}</button></div>{(!status || status.connection_uncertain || !status.running) && <p className="text-xs text-amber-200">Đang hiển thị tài khoản đã lưu. Chưa xác minh được kết nối gateway; không cần thêm lại tài khoản.</p>}<p className="text-xs text-slate-400">Chế độ hiện tại: tối đa {status?.performance?.max_accounts || 3} tài khoản, {status?.performance?.videos_per_account || 2} video/tài khoản. Khi đang viết prompt, dành riêng một tài khoản viết; viết xong tài khoản đó tham gia tạo video. Chỉ thay tài khoản không còn khả dụng. Giãn gửi riêng 1–2 giây.</p>{accounts.map(account => <div key={account.id} className="flex flex-wrap items-center gap-3 text-sm"><span className="flex-1 min-w-0 break-words">{account.label || account.id} · {account.quota_exhausted ? 'Hết hạn mức · Tạm ngừng giao việc' : account.status === 'active' ? 'Khả dụng' : account.status === 'invalid' ? 'Cần đăng nhập lại' : 'Tạm nghỉ'} · {account.enabled ? 'Đang bật' : 'Đã tắt'} · {account.work_role === 'prompt' ? 'Đang viết prompt' : account.work_role === 'video' ? 'Đang tạo video' : 'Dự phòng'}</span><div className="w-44 shrink-0 text-xs leading-5" title={account.additional_tokens?.error || 'Token bổ sung, không phải số lượt video 24 giờ'}><div className="text-slate-400">Token bổ sung</div><strong className={account.additional_tokens?.remaining_label === '0' ? 'text-red-300' : 'text-emerald-200'}>{account.token_loading ? 'Đang đọc…' : account.additional_tokens?.error ? 'Không rõ' : account.additional_tokens?.remaining_label ? `Còn ${account.additional_tokens.remaining_label}` : 'Chưa kiểm tra'}</strong>{account.additional_tokens?.checked_at && <div className="text-slate-500">{account.additional_tokens.error ? 'Số liệu cũ · ' : 'Cập nhật '}{new Date(account.additional_tokens.checked_at * 1000).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}</div>}</div><button className={button} disabled={!!busy} onClick={() => setAccountName(account.label)}>Đăng nhập lại</button><button className={button} disabled={!!busy} onClick={() => run('Đang cập nhật tài khoản…', async () => { setAccounts(await call<Account[]>('/accounts/' + account.id + '/enabled', { enabled: !account.enabled })) })}>{account.enabled ? 'Tắt' : 'Bật'}</button><button className={button + ' text-red-300 border-red-400/40'} disabled={!!busy} onClick={() => { if (!confirm(`Xóa tài khoản “${account.label || account.id}” khỏi ứng dụng? Video và prompt đã tạo vẫn được giữ. Bạn có thể đăng nhập lại để thêm tài khoản sau.`)) return; run('Đang xóa tài khoản…', async () => { setAccounts(await call<Account[]>('/accounts/' + account.id + '/delete', {})); setNotice('Đã xóa tài khoản khỏi ứng dụng. Video và prompt được giữ nguyên.') }) }}>Xóa</button></div>)}<label className="block text-sm">Tên tài khoản thêm mới / đăng nhập lại<input className={field + ' mt-2'} value={accountName} maxLength={80} onChange={e => setAccountName(e.target.value)} placeholder="Ví dụ: Muse 2" /></label><p className="text-xs text-slate-400">Dùng lại tên cũ để cập nhật phiên; dùng tên mới để thêm tài khoản. Mỗi tài khoản cần là một tài khoản Muse riêng.</p></div><label className="flex gap-2 items-start text-sm"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /><span>Cho phép lưu phiên Muse trên máy để sử dụng cho các lần tiếp theo.</span></label>
      <div className="flex gap-2 flex-wrap">
        <button className={button} disabled={!!busy || !consent || !accountName.trim()} onClick={() => run('Đang mở Chrome đăng nhập…', async () => { await call('/login/start', { label: accountName.trim() }); setNotice('Đăng nhập Muse trong cửa sổ Chrome vừa mở. Sau đó quay lại bấm Tôi đã đăng nhập.') })}>Mở Chrome đăng nhập</button>
        <button className={button} disabled={!!busy || !consent} onClick={() => run('Đang kết nối phiên…', async () => { await call('/login/finish', { consent: true }); setNotice('Đã lưu phiên. Gửi một câu thử để kiểm tra tài khoản Muse thật.') })}>Tôi đã đăng nhập — Kết nối</button>
      </div>
      <details className="text-sm space-y-3"><summary className="cursor-pointer">Nhập phiên thủ công khi đăng nhập tự động không dùng được</summary>
        <p className="mt-3 opacity-70">Chrome đã đăng nhập muse.ai → F12 → Application → Cookies → https://muse.ai. Nhập các giá trị bên dưới trên máy, không gửi vào chat. hatch_gw không bắt buộc nếu Muse không cấp.</p>
        {names.map(name => <label className="block mt-3" key={name}>{name}{name === 'hatch_gw' ? ' (không bắt buộc)' : ''}<input type="password" autoComplete="off" className={field + ' mt-1'} value={cookies[name] || ''} onChange={e => setCookies(old => ({ ...old, [name]: e.target.value }))} /></label>)}
        <button className={button + ' mt-3'} disabled={!!busy || !consent || requiredNames.some(name => !cookies[name]?.trim())} onClick={() => run('Đang lưu phiên…', async () => { await call('/session', { cookies, consent: true, label: accountName.trim() }); setCookies({}); setNotice('Đã lưu phiên trên máy. Gửi một câu thử để xác minh.') })}>Lưu phiên Muse</button>
      </details>
    </section>
    {busy && <p role="status">{busy}</p>}{error && <p role="alert" className="rounded-lg border border-red-500 p-3 text-sm whitespace-pre-wrap">{error}</p>}{notice && <p role="status" className="rounded-lg border p-3 text-sm">{notice}</p>}
    {!connectionOnly && <><section className="rounded-xl border p-5 space-y-4">
      <h2 className="font-semibold">2. Thử nội dung và tạo media</h2>
      <div className="flex gap-3"><select className="rounded border p-2 bg-transparent" value={mode} onChange={e => setMode(e.target.value as typeof mode)}><option value="chat">Nội dung / kịch bản</option><option value="image">Tạo ảnh</option><option value="video">Ảnh → video (8 giây)</option></select>
        {mode !== 'chat' && <select className="rounded border p-2 bg-transparent" value={size} onChange={e => setSize(e.target.value)}><option>16:9</option><option>9:16</option><option>1:1</option></select>}</div>
      <textarea className={field + ' min-h-32'} value={prompt} maxLength={20000} onChange={e => setPrompt(e.target.value)} placeholder="Thử kết nối: Hãy trả lời ngắn bằng tiếng Việt: Muse đã kết nối. Hoặc nhập nội dung cần viết / prompt tạo ảnh, video." />
      {mode !== 'chat' && <div className="space-y-2"><label className="block text-sm">{mode === 'video' ? 'Ảnh đầu (bắt buộc; chỉ dùng ảnh đầu tiên)' : 'Ảnh tham chiếu (tùy chọn, tối đa 4 ảnh)'}</label><input type="file" accept="image/png,image/jpeg,image/webp" multiple={mode === 'image'} onChange={e => { selectFiles(e.target.files).catch(() => setError('Không đọc được ảnh.')) }} />
        <div className="flex gap-2">{references.map((ref, i) => <img src={ref} key={i} alt={`Ảnh tham chiếu ${i + 1}`} className="h-20 w-20 object-cover rounded" />)}</div></div>}
      <p className="text-xs opacity-70">Yêu cầu được gửi tới tài khoản Muse thật và có thể dùng hạn mức. Tỉ lệ, thời lượng và model thực tế tùy khả năng Muse; có thể mô tả thêm trong prompt.</p>
      <button className={button} disabled={!!busy || !status?.ready || !prompt.trim() || (mode === 'video' && !references.length)} onClick={submit}>{mode === 'chat' ? 'Gửi nội dung tới Muse' : mode === 'image' ? 'Tạo 1 ảnh' : 'Tạo 1 video từ ảnh'}</button>
      {answer && <div className="rounded-lg border p-4 whitespace-pre-wrap text-sm">{answer}<button className={button + ' block mt-3'} onClick={() => navigator.clipboard.writeText(answer).catch(() => setError('Không sao chép được; hãy chọn nội dung và sao chép thủ công.'))}>Sao chép nội dung</button></div>}
    </section>
    <section className="space-y-4"><div className="flex items-center justify-between"><h2 className="font-semibold">3. Lịch sử ảnh / video</h2><button className={button} disabled={!!busy} onClick={() => run('Đang nạp lịch sử…', async () => { setJobs(await call<Job[]>('/tasks')) })}>Nạp lại lịch sử</button></div>
      <p className="text-xs opacity-70">Giữ ứng dụng và gateway đang chạy khi tạo media. Đóng ứng dụng có thể làm gián đoạn tác vụ; Muse vẫn có thể tiếp tục xử lý phía dịch vụ. Tải kết quả rồi nhập vào dự án FrameWeaver để dựng tiếp.</p>
      {!jobs.length && <p className="text-sm opacity-60">Chưa có tác vụ Muse.</p>}
      {jobs.slice(0, 30).map(job => <article key={job.id} className="rounded-xl border p-4 space-y-3"><div className="text-xs opacity-60">{job.kind === 'image' ? 'Ảnh' : 'Video'} · {job.status || 'Đang kiểm tra'} · {job.progress || 0}%</div><p className="text-sm whitespace-pre-wrap">{job.prompt}</p>{job.error && <p className="text-sm text-red-400">{job.error}</p>}{job.media?.map(name => <Media key={name} name={name} kind={job.kind} />)}</article>)}
    </section></>}
  </div>
}

