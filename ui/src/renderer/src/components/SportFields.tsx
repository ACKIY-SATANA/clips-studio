import { t } from '../lib/i18n'
import { fitSport, rememberSport } from '../lib/sports'
import type { SportChoice, SportOption } from '../lib/types'

/** The Sports toggle's choices, under a video or a watched channel: which
 *  sport, which moments to keep, which part of the match, and who to favour.
 *  Rendered into the caller's row, the way Longform's output choice is. */
export default function SportFields({
  value,
  sports,
  onChange,
  remember = false,
  name
}: {
  value: SportOption
  sports: SportChoice[]
  onChange: (next: SportOption) => void
  /** Keep the choice for the next video (the Generate list does). */
  remember?: boolean
  /** Tells the controls apart when there are several rows ("video 2"). */
  name?: string
}): JSX.Element {
  const sport = sports.find((s) => s.id === value.name)
  const suffix = name ? ` ${name}` : ''
  const set = (change: Partial<SportOption>): void => {
    const next = fitSport({ ...value, ...change }, sports)
    if (!next) return
    if (remember) rememberSport(next)
    onChange(next)
  }
  return (
    <>
      <span className="label shrink-0">{t('Sport')}</span>
      <select
        className="input !w-36"
        value={value.name}
        onChange={(e) => set({ name: e.target.value, highlights: undefined, period: undefined })}
        aria-label={`${t('Sport')}${suffix}`}
      >
        {sports.map((s) => (
          <option key={s.id} value={s.id}>
            {t(s.label)}
          </option>
        ))}
      </select>
      <span className="label shrink-0">{t('Highlights')}</span>
      <select
        className="input !w-52"
        value={value.highlights ?? ''}
        onChange={(e) => set({ highlights: e.target.value })}
        aria-label={`${t('Highlights')}${suffix}`}
        title={t('Which moments become clips. A moment type is only claimed when the scoreboard or two signals agree; the rest are kept as big moments.')}
      >
        {(sport?.highlights ?? []).map((h) => (
          <option key={h.id} value={h.id}>
            {t(h.label)}
          </option>
        ))}
      </select>
      <span className="label shrink-0">{t('Period')}</span>
      <select
        className="input !w-36"
        value={value.period ?? ''}
        onChange={(e) => set({ period: e.target.value })}
        aria-label={`${t('Period')}${suffix}`}
        title={t('Which part of the match. Read from the scoreboard clock; a moment whose half can’t be told is kept and marked.')}
      >
        {(sport?.periods ?? []).map((p) => (
          <option key={p.id} value={p.id}>
            {t(p.label)}
          </option>
        ))}
      </select>
      {value.highlights === 'custom' && (
        <input
          className="input !w-72 max-w-full"
          placeholder={t('Describe the moments you want')}
          aria-label={`${t('Describe the moments you want')}${suffix}`}
          maxLength={200}
          value={value.request ?? ''}
          onChange={(e) => set({ request: e.target.value })}
          title={t('For example: the saves and the late chances. It adds points to those moments, like a clip direction; nothing else is left out for it.')}
        />
      )}
      <input
        className="input !w-56 max-w-full"
        placeholder={t('Teams or players (optional)')}
        aria-label={`${t('Teams or players')}${suffix}`}
        maxLength={200}
        value={value.teams ?? ''}
        onChange={(e) => set({ teams: e.target.value })}
        title={t('Clips where the commentary names them get extra points. Nothing is left out for it, and nobody is guessed.')}
      />
    </>
  )
}
