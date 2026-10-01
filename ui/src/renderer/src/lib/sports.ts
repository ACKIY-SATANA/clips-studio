import { useEffect, useState } from 'react'
import { api } from './api'
import type { SportChoice, SportOption, SubScores } from './types'

/** The sports the engine offers (GET /sports), asked once and shared by every
 *  Sports control and the queue's chips. Empty when the engine has no sports
 *  package, which hides the toggle: nothing else depends on it. */
let offered: SportChoice[] | null = null
let asking: Promise<SportChoice[] | null> | null = null

function ask(): Promise<SportChoice[] | null> {
  if (offered) return Promise.resolve(offered)
  asking ??= api
    .sports()
    .then((list) => (offered = Array.isArray(list) ? list : []))
    .catch(() => null) // the engine isn't up yet: asked again shortly
    .finally(() => {
      asking = null
    })
  return asking
}

/** The sports on offer; null until the engine has answered. Keeps asking
 *  while the engine is still starting, so the toggle appears once it's up
 *  rather than staying hidden until the page is reopened. */
export function useSports(): SportChoice[] | null {
  const [list, setList] = useState<SportChoice[] | null>(offered)
  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const load = (): void => {
      void ask().then((got) => {
        if (!live) return
        if (got) setList(got)
        else timer = setTimeout(load, 3000)
      })
    }
    load()
    return () => {
      live = false
      if (timer) clearTimeout(timer)
    }
  }, [])
  return list
}

/** An option made valid against what the engine offers: a highlights
 *  choice it doesn't have falls back to its first. Null when the sport itself
 *  isn't offered. The whole match is always clipped and the footage is told
 *  apart by itself, so neither is sent; Custom isn't offered either (the box
 *  at the bottom says what the clips should be about, in words). Text is kept
 *  as typed (trimmed on the engine), so a space between two words survives
 *  the keystroke. */
export function fitSport(o: SportOption, list: SportChoice[]): SportOption | null {
  const sport = list.find((s) => s.id === o.name)
  if (!sport) return null
  const offered = sport.highlights.filter((h) => h.id !== 'custom')
  const highlights = offered.some((h) => h.id === o.highlights) ? o.highlights : offered[0]?.id
  const reels = REELS.map((r) => r.id).filter((id) => (o.reels ?? []).includes(id))
  return {
    name: sport.id,
    ...(highlights ? { highlights } : {}),
    ...(o.teams ? { teams: o.teams } : {}),
    ...(o.events && o.events.trim() ? { events: o.events } : {}),
    ...(reels.length ? { reels } : {})
  }
}

/** What each Highlights choice keeps, shown under its name in the list. */
export const HIGHLIGHT_HINTS: Record<string, string> = {
  best: 'The match’s biggest moments, of any kind',
  goals: 'Every goal, with its build-up and celebration',
  goals_celebrations: 'Every goal, with a longer celebration after it',
  saves: 'The goalkeepers’ best saves',
  chances: 'Near misses, big chances and shots',
  attacking: 'Goals, chances, shots and set pieces',
  cards: 'Yellow and red cards, and VAR checks',
  penalties: 'Every penalty, scored or missed'
}

/** Each sport's icon in the Sport menu. */
export const SPORT_ICONS: Record<string, string> = { soccer: '⚽' }

/** A sport's name as the app shows it, where it differs from the engine's
 *  (which also goes into the scoring prompt, so it stays as it is). */
const SPORT_NAMES: Record<string, string> = { soccer: 'Soccer / Football' }

export function sportName(s: { id: string; label: string }): string {
  return SPORT_NAMES[s.id] ?? s.label
}

/** Sports on the way: listed under the ones on offer, greyed out, to hint at
 *  what's next. UI only, so one can never be sent in a job. */
export const COMING_SOON: { label: string; icon: string }[] = [
  { label: 'Basketball', icon: '🏀' },
  { label: 'Cricket', icon: '🏏' }
]

/** The story reels a match can have joined from its clips, in their order. */
export const REELS: { id: string; label: string; title: string }[] = [
  {
    id: 'recap',
    label: 'Match recap',
    title: 'Every goal, card and save of the match in one video, in match order.'
  },
  {
    id: 'teams',
    label: 'Team reels',
    title: 'A video per team of its moments: the goals the score box or your match events give it.'
  },
  {
    id: 'players',
    label: 'Player reels',
    title: 'A video per player named in two moments or more: by your match events, or by the commentary for a name in Teams or players.'
  }
]

const LAST = 'generate-sport-choice'

/** The sport, highlights and reels last chosen on the Generate list. Teams
 *  and match events belong to one match, so they aren't kept. */
export function lastSport(): SportOption | null {
  try {
    const raw = JSON.parse(localStorage.getItem(LAST) ?? 'null')
    return raw && typeof raw.name === 'string'
      ? {
          name: raw.name,
          highlights: raw.highlights,
          ...(Array.isArray(raw.reels) && raw.reels.length ? { reels: raw.reels.map(String) } : {})
        }
      : null
  } catch {
    return null
  }
}

export function rememberSport(o: SportOption): void {
  try {
    localStorage.setItem(LAST, JSON.stringify({ name: o.name, highlights: o.highlights, reels: o.reels }))
  } catch {
    // Not remembered for next time; this video still gets it.
  }
}

/** What the Sports toggle starts with: the last choice while it's still
 *  offered, else the first sport's first highlights. */
export function startingSport(list: SportChoice[]): SportOption | null {
  const last = lastSport()
  const sport = list.find((s) => s.id === last?.name) ?? list[0]
  if (!sport) return null
  return fitSport(last?.name === sport.id ? last : { name: sport.id }, list)
}

const titled = (id: string): string => id.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())

/** "Sports · Soccer / Football · All goals · 2nd half · Team A", for the queue's chip. */
export function describeSport(o: SportOption): string {
  const sport = offered?.find((s) => s.id === o.name)
  const named = (id: string, from: { id: string; label: string }[] | undefined): string =>
    from?.find((x) => x.id === id)?.label ?? titled(id)
  const parts = ['Sports', sport ? sportName(sport) : titled(o.name)]
  if (o.highlights) parts.push(named(o.highlights, sport?.highlights))
  if (o.period && o.period !== 'full') parts.push(named(o.period, sport?.periods))
  if (o.teams) parts.push(o.teams.length > 30 ? `${o.teams.slice(0, 30)}…` : o.teams)
  if (o.events) parts.push('match events')
  for (const reel of REELS) if (o.reels?.includes(reel.id)) parts.push(reel.label.toLowerCase())
  return parts.join(' · ')
}

/** "Goal · 18' · HOM" for a clip: the moment it is, when, and whose. The
 *  match minute when the scoreboard's clock was read, else the time into
 *  the video. Null for a clip that isn't a match moment. */
export function sportMoment(s: SubScores | undefined): string | null {
  if (!s?.sport_label) return null
  // A story reel: what it is and how many moments it joins.
  if (s.sport_reel) return `${s.sport_label}${s.sport_parts ? ` · ${s.sport_parts} moments` : ''}`
  let when = ''
  if (s.sport_minute != null) when = `${s.sport_minute}'`
  else if (s.sport_t != null) {
    const t = Math.round(s.sport_t)
    const h = Math.floor(t / 3600)
    const m = Math.floor((t % 3600) / 60)
    const sec = String(t % 60).padStart(2, '0')
    when = h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
  }
  const parts = [s.sport_label, when, s.sport_team ?? s.sport_player ?? ''].filter(Boolean)
  return `${parts.join(' · ')}${s.sport_replay ? ' (replay)' : ''}`
}
