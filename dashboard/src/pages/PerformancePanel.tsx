import { Activity, Cpu, Gauge, MemoryStick } from 'lucide-react'

export type PerformanceSettings = {
  preset: string; max_accounts: number; videos_per_account: number; max_videos: number; automatic: boolean
}
export type AdaptiveStatus = {
  enabled: boolean; target_jobs: number; ceiling: number; active_jobs: number; paused: boolean;
  cpu_percent: number | null; ram_percent: number | null; free_gb: number | null; reason: string
}

export function PerformanceSettingsPanel({ value, disabled, onChange }: {
  value: PerformanceSettings; disabled: boolean; onChange: (preset: string, automatic: boolean) => void
}) {
  return <section className="performance-settings">
    <label className="landscape-label"><span className="flex items-center gap-2"><Gauge size={15} />Hiệu năng máy</span>
      <select className="landscape-input mt-2" value={value.preset} disabled={disabled}
        onChange={e => onChange(e.target.value, value.automatic)}>
        <option value="eco">Tiết kiệm · tối đa 2 video</option>
        <option value="balanced">Cân bằng · tối đa 6 video</option>
        <option value="fast">Nhanh · tối đa 15 video</option>
      </select>
    </label>
    <label className="performance-toggle"><input type="checkbox" checked={value.automatic} disabled={disabled}
      onChange={e => onChange(value.preset, e.target.checked)} />
      <span><strong>Tự điều phối theo tải máy</strong><small>Giảm luồng khi CPU/RAM cao; tăng dần khi máy ổn định.</small></span>
    </label>
    <p className="landscape-hint">Giới hạn {value.max_accounts} tài khoản × {value.videos_per_account} video. Đổi thiết lập khi đã dừng công việc.</p>
  </section>
}

function Meter({ label, value, icon }: { label: string; value: number | null; icon: React.ReactNode }) {
  return <div className="load-meter"><div><span>{icon}{label}</span><strong>{value == null ? '—' : `${Math.round(value)}%`}</strong></div>
    <progress aria-label={`${label} toàn máy`} max={100} value={value ?? 0} className={value != null && value >= 90 ? 'load-high' : ''} />
  </div>
}

export function AdaptiveStatusPanel({ status, enabled, ceiling }: { status: AdaptiveStatus | null; enabled: boolean; ceiling: number }) {
  const draining = status != null && status.active_jobs > status.target_jobs
  return <section className={'adaptive-status-panel' + (status?.paused ? ' resource-paused' : '')} aria-label="Điều phối và tải máy">
    <div className="adaptive-copy"><div className="flex items-center gap-2"><Activity size={16} /><strong>{enabled ? 'Điều phối tự động' : 'Giới hạn thủ công'}</strong>
      <span className="landscape-badge">{status?.paused ? 'Chờ RAM giảm' : draining ? 'Đang giảm luồng' : !status ? 'Đang chờ' : status.active_jobs ? 'Đang xử lý' : 'Sẵn sàng'}</span></div>
      <p>{status?.reason || 'Đang chờ kết nối để đo tải máy.'}</p>
      <small>Chỉ điều chỉnh việc mới. Các tác vụ đã gửi vẫn được giữ.</small>
    </div>
    <div className="adaptive-slots"><span>Đang chạy / mục tiêu</span><strong>{status?.active_jobs ?? 0}<i> / </i>{status?.target_jobs ?? '—'}</strong><small>{draining ? 'Chờ tác vụ cũ hoàn tất' : `Trần đã chọn: ${ceiling} tác vụ`}</small></div>
    <div className="adaptive-meters"><Meter label="CPU" value={status?.cpu_percent ?? null} icon={<Cpu size={13} />} />
      <Meter label="RAM" value={status?.ram_percent ?? null} icon={<MemoryStick size={13} />} />
      <small>{status?.free_gb == null ? 'Số liệu toàn máy · mỗi 5 giây' : `RAM trống ${status.free_gb.toFixed(1)} GB · mỗi 5 giây`}</small>
    </div>
  </section>
}
