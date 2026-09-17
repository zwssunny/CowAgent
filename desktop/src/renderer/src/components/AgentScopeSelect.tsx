import React, { useEffect, useRef, useState } from 'react'
import { ChevronDown, Check } from 'lucide-react'
import { t } from '../i18n'
import { useAgentStore, selectMultiAgent, enabledDefaultFirst } from '../store/agentStore'
import AgentAvatar from './AgentAvatar'

interface AgentScopeSelectProps {
  /** The Agent whose data is currently shown. */
  value: string
  onChange: (agentId: string) => void
}

/**
 * A compact Agent picker used by the Knowledge and Memory pages to scope which
 * Agent's data is shown. Mirrors the web console's per-page agent select: an
 * avatar + name trigger opening a list of every Agent in the roster.
 *
 * Renders nothing in single-Agent mode, so those pages look exactly as they did
 * before the multi-Agent upgrade.
 */
const AgentScopeSelect: React.FC<AgentScopeSelectProps> = ({ value, onChange }) => {
  const multiAgent = useAgentStore(selectMultiAgent)
  const agents = useAgentStore((s) => s.agents)
  const defaultAgentId = useAgentStore((s) => s.defaultAgentId)
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  if (!multiAgent) return null

  // Default first, matching every other Agent picker.
  const ordered = enabledDefaultFirst(agents, defaultAgentId)

  const current = agents.find((a) => a.id === value) || null

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1.5 h-8 pl-1 pr-2 rounded-btn border text-[13px] cursor-pointer transition-colors ${
          open ? 'border-accent bg-accent-soft text-accent' : 'border-strong text-content-secondary hover:bg-inset-2'
        }`}
        title={t('scope_agent_tip')}
      >
        {current ? <AgentAvatar agent={current} size={18} /> : null}
        <span className="max-w-[128px] truncate">{current?.name || current?.id || t('scope_agent_all')}</span>
        <ChevronDown size={12} className={`opacity-60 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-56 max-h-[360px] overflow-y-auto rounded-xl border border-default bg-elevated shadow-xl z-30 p-1">
          {ordered.map((a) => {
            const active = a.id === value
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => {
                  onChange(a.id)
                  setOpen(false)
                }}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left cursor-pointer transition-colors ${
                  active ? 'bg-accent-soft text-accent' : 'hover:bg-inset text-content'
                }`}
              >
                <AgentAvatar agent={a} size={20} />
                <span className="flex-1 min-w-0 truncate text-[13px]">{a.name || a.id}</span>
                {a.id === defaultAgentId && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-600 flex-shrink-0">
                    {t('agents_default_badge')}
                  </span>
                )}
                {active && <Check size={13} className="shrink-0" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default AgentScopeSelect
