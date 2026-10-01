import { useState } from 'react'
import { t } from '../lib/i18n'
import { COMING_SOON, REELS, SPORT_ICONS, fitSport, rememberSport, sportName } from '../lib/sports'
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
  const [eventsOpen, setEventsOpen] = useState(Boolean(value.events))
  const listed = (value.events ?? '').split('\n').filter((line) => line.trim()).length
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
        className="input !w-48"
        value={value.name}
        onChange={(e) => set({ name: e.target.value, highlights: undefined, period: undefined })}
        aria-label={`${t('Sport')}${suffix}`}
      >
        {sports.map((s) => (
          <option key={s.id} value={s.id}>
            {SPORT_ICONS[s.id] ? `${SPORT_ICONS[s.id]} ` : ''}
            {t(sportName(s))}
          </option>
        ))}
        {COMING_SOON.map((s) => (
          <option key={s.label} value="" disabled>
            {`${s.icon} ${t(s.label)} (${t('coming soon')})`}
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
      {(sport?.footage ?? []).length > 0 && (
        <>
          <span className="label shrink-0">{t('Footage')}</span>
          <select
            className="input !w-40"
            value={value.footage ?? 'auto'}
            onChange={(e) => set({ footage: e.target.value })}
            aria-label={`${t('Footage')}${suffix}`}
            title={t('A TV broadcast has a score box and commentary to confirm the goals. A club camera or a phone at the touchline usually has neither: its clips follow the ball, and its goals come from the match events you add. Automatic tells them apart by the score box.')}
          >
            {(sport?.footage ?? []).map((f) => (
              <option key={f.id} value={f.id}>
                {t(f.label)}
              </option>
            ))}
          </select>
        </>
      )}
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
        title={t('Clips where the commentary names them get extra points. Nothing is left out for it, and nobody is guessed. With Player reels, a name the commentary says in two moments or more gets a reel of its own.')}
      />
      <span className="label shrink-0">{t('Also make')}</span>
      {REELS.map((reel) => (
        <label key={reel.id} className="flex items-center gap-1.5 text-sm cursor-pointer shrink-0" title={t(reel.title)}>
          <input
            type="checkbox"
            className="size-4 accent-[#38BDF8]"
            aria-label={`${t(reel.label)}${suffix}`}
            checked={(value.reels ?? []).includes(reel.id)}
            onChange={(e) => {
              const others = (value.reels ?? []).filter((id) => id !== reel.id)
              set({ reels: e.target.checked ? [...others, reel.id] : others })
            }}
          />
          {t(reel.label)}
        </label>
      ))}
      <button
        type="button"
        className="btn-ghost !py-1 shrink-0"
        aria-expanded={eventsOpen}
        onClick={() => setEventsOpen(!eventsOpen)}
        title={t('The match’s goals and other moments as you have them: from your club app, the match report or the video’s description. Each one becomes a clip, placed by the clock on screen, or by the kick-off times you list.')}
      >
        {t('Match events')}
        {listed > 0 ? ` (${listed})` : ''} {eventsOpen ? '▾' : '▸'}
      </button>
      {eventsOpen && (
        <textarea
          className="input basis-full min-h-28 font-mono text-xs"
          placeholder={
            'One per line, as your club app, the match report or the video’s description has them:\n' +
            '09:22 Kick off\n18:16 Goal Player A\n45+2\' Yellow card Team B\n1:00:40 Second half'
          }
          aria-label={`${t('Match events')}${suffix}`}
          maxLength={4000}
          value={value.events ?? ''}
          onChange={(e) => set({ events: e.target.value })}
        />
      )}
    </>
  )
}
