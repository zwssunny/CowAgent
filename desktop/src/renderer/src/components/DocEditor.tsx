import React, { useEffect, useLayoutEffect } from 'react'
import { AlertTriangle, Loader2, Pencil, RotateCcw, Save, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { t } from '../i18n'
import { useConfirmStore } from '../store/confirmStore'
import type { DocEditorStore } from '../store/docEditorStore'

/**
 * Text area for a document page's editor, and the header buttons that drive it.
 *
 * The counterpart of the preview panel's FileEditor, for the pages that show one
 * document at a time (memory files, skill definitions) rather than a file tree.
 */
export function DocEditor<D>({
  store,
  textareaRef: ref,
}: {
  store: DocEditorStore<D>
  /** Owned by the page so its Save button can read the current text. */
  textareaRef: React.RefObject<HTMLTextAreaElement>
}): React.ReactElement | null {
  const edit = store((s) => s.edit)
  const setDirty = store((s) => s.setDirty)
  const stashText = store((s) => s.stashText)
  const save = store((s) => s.save)
  const cancelEdit = store((s) => s.cancelEdit)
  const pendingConfirm = useConfirmStore((s) => s.pending)

  const baseline = edit?.baseline

  // autoFocus covers the normal mount. This also hands focus back once a dialog
  // that took it (discard / overwrite) has closed, so typing resumes without a
  // click. Keyed on the dialog rather than running every render, which would
  // fight the user for focus on the header buttons.
  useLayoutEffect(() => {
    const el = ref.current
    if (!pendingConfirm && el && document.activeElement !== el) el.focus()
  }, [pendingConfirm])

  // Leaving the page unmounts the text area; hand the work in progress back to
  // the store so returning restores it rather than losing it.
  useEffect(() => {
    const el = ref.current
    return () => {
      if (el) stashText(el.value)
    }
  }, [])

  // A save in place moves the baseline. Re-derive from the text area rather than
  // trusting the store's `dirty: false`, in case the user kept typing while the
  // write was in flight.
  useEffect(() => {
    if (ref.current && baseline !== undefined) setDirty(ref.current.value !== baseline)
  }, [baseline])

  if (!edit) return null

  const onChange = () => setDirty((ref.current?.value ?? '') !== edit.baseline)

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      // Save in place, the way an editor does. The Save button in the header
      // instead returns to the rendered document.
      e.preventDefault()
      void save(e.currentTarget.value, { keepEditing: true })
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      void cancelEdit()
      return
    }
    if (e.key === 'Tab') {
      // Otherwise Tab moves focus out of the text area, which is never what
      // indenting a line is meant to do.
      e.preventDefault()
      const el = e.currentTarget
      const { selectionStart: start, selectionEnd: end } = el
      el.value = `${el.value.slice(0, start)}    ${el.value.slice(end)}`
      el.selectionStart = el.selectionEnd = start + 4
      onChange()
    }
  }

  return (
    <div className="h-full flex flex-col">
      {edit.error && (
        <div className="shrink-0 flex items-start gap-1.5 px-4 py-2 text-[12px] text-red-500 bg-red-500/10 border-b border-default">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span className="break-all">{edit.error}</span>
        </div>
      )}
      <textarea
        ref={ref}
        // Uncontrolled: React seeds the node and then leaves the text alone, so
        // typing never round-trips through a re-render.
        defaultValue={edit.loaded}
        autoFocus
        onChange={onChange}
        onKeyDown={onKeyDown}
        spellCheck={false}
        // Wrapped rather than scrolling sideways: these are prose documents, and
        // a horizontal scrollbar hides the end of every long paragraph.
        className="flex-1 min-h-0 w-full p-4 bg-transparent text-content font-mono text-[12.5px] leading-relaxed border-0 outline-none resize-none whitespace-pre-wrap overflow-x-hidden overflow-y-auto"
        // `anywhere` covers the unbreakable cases (a long URL) that wrapping on
        // its own would still push off the right edge.
        style={{ tabSize: 4, overflowWrap: 'anywhere' }}
      />
    </div>
  )
}

/**
 * Edit / Save / Discard for a document page's header.
 *
 * Which buttons appear is derived from the store, so a page only has to place
 * this once and the two modes stay in step.
 */
export function DocActions<D>({
  store,
  textareaRef: ref,
}: {
  store: DocEditorStore<D>
  textareaRef: React.RefObject<HTMLTextAreaElement>
}): React.ReactElement | null {
  const doc = store((s) => s.doc)
  const edit = store((s) => s.edit)
  const readonly = store((s) => s.readonly)
  const loading = store((s) => s.loading)
  const startEdit = store((s) => s.startEdit)
  const save = store((s) => s.save)
  const cancelEdit = store((s) => s.cancelEdit)

  if (!doc) return null

  if (!edit) {
    if (readonly || loading) return null
    return (
      // The long form carries the keyboard hints, which don't fit on the button.
      <DocBtn onClick={() => void startEdit()} icon={Pencil} title={t('ws_edit')}>
        {t('doc_edit')}
      </DocBtn>
    )
  }

  return (
    <>
      <DocBtn
        primary
        busy={edit.saving}
        // Never fall back to '' for a missing text area: that would write an
        // empty file over the user's content.
        onClick={() => {
          const el = ref.current
          if (el) void save(el.value)
        }}
        icon={edit.saving ? Loader2 : Save}
      >
        {t('doc_edit_save')}
      </DocBtn>
      <DocBtn onClick={() => void cancelEdit()} icon={RotateCcw}>
        {t('ws_edit_cancel')}
      </DocBtn>
    </>
  )
}

const DocBtn: React.FC<{
  onClick: () => void
  icon: LucideIcon
  primary?: boolean
  busy?: boolean
  title?: string
  children: React.ReactNode
}> = ({ onClick, icon: Icon, primary, busy, title, children }) => (
  <button
    onClick={onClick}
    disabled={busy}
    title={title}
    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn text-sm transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-default ${
      primary
        ? 'bg-accent text-white hover:opacity-90'
        : 'text-content-secondary hover:bg-inset border border-strong'
    }`}
  >
    <Icon size={14} className={busy ? 'animate-spin' : undefined} />
    {children}
  </button>
)

/** The reason an edit was refused, or a read that failed. */
export function DocNotice<D>({ store }: { store: DocEditorStore<D> }): React.ReactElement | null {
  const notice = store((s) => s.notice)
  const dismissNotice = store((s) => s.dismissNotice)

  if (!notice) return null

  return (
    <div className="shrink-0 flex items-start gap-1.5 px-6 py-2 text-[12px] text-amber-600 bg-amber-500/10 border-b border-default">
      <AlertTriangle size={13} className="mt-0.5 shrink-0" />
      <span className="flex-1 break-all">{notice}</span>
      <button onClick={dismissNotice} title={t('ws_close')} className="shrink-0 opacity-60 hover:opacity-100 cursor-pointer">
        <X size={13} />
      </button>
    </div>
  )
}
