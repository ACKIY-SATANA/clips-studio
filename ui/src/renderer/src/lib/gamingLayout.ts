/** Gaming / Reaction geometry for the layout editor's preview.
 *
 *  Mirrors gaming/layout.py plan() and gaming/framing.py cam_crop() line for
 *  line, so the preview beside the boxes you drag shows exactly the crops the
 *  render will make, face shift included. A test runs this file under Node
 *  and compares every number with the Python (tests/test_ui_gaming_layout_sync.py). */

import { LAYOUTS } from './gamingLayouts'
import type { FrameBox } from './types'

export const OUT_W = LAYOUTS.canvas[0]
export const OUT_H = LAYOUTS.canvas[1]
const HEADROOM = LAYOUTS.headroom
const MAX_SHIFT = 0.3
const PIP_GAP = 24
const PIP_MARGIN = 0.02

/** [x, y, w, h] in pixels (source or canvas). */
export type PxBox = [number, number, number, number]
/** The streamer's head in source px: [centre x, top, chin]. */
export type Head = [number, number, number]
export type Role = 'cam' | 'cam2' | 'game' | 'ui'

export interface SafeZone {
  top: number
  bottom: number
  left: number
  right: number
}

export interface Element {
  role: Role
  src: PxBox
  dest: PxBox
  fit: 'cover' | 'contain'
  anchor: 'top' | 'bottom' | 'center'
  shift: number
  shape: 'rect' | 'circle'
}

export interface GamingPlan {
  preset: string
  elements: Element[]
  order: 'cam_top' | 'game_top'
  safe: string
}

/** The settings plan() reads; the same keys as render_opts.gaming. */
export interface LayoutSettings {
  preset?: string
  order?: string
  divider?: number
  safe?: string
  game_fit?: string
  game_align?: string
  cam?: FrameBox | null
  cam2?: FrameBox | null
  game_box?: FrameBox | null
  ui_box?: FrameBox | null
  cam_position?: string
}

type Spec = {
  label: string
  type: 'stack' | 'full' | 'pip'
  rows?: readonly (readonly string[])[]
  divider?: readonly number[]
  ui_share?: number
  order?: string
  game_fit?: string
  cams?: readonly string[]
  pip_width?: number
  pip_aspect?: number
  shape?: string
}

export const PRESETS = LAYOUTS.presets as unknown as Record<string, Spec>
export const SAFE_ZONES = LAYOUTS.safe_zones as unknown as Record<string, SafeZone & { label: string }>

// Python's int(v) // 2 * 2, for the positive values used here.
const even = (v: number): number => Math.max(2, Math.floor(Math.trunc(v) / 2) * 2)
const pos = (v: number): number => Math.max(0, Math.floor(Math.trunc(v) / 2) * 2)
const clamp = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, v))
/** Python's round(): halves go to the even neighbour. */
const roundHalfEven = (v: number): number => {
  const f = Math.floor(v)
  const d = v - f
  if (Math.abs(d - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1
  return Math.round(v)
}

export function safeZone(name?: string | null): SafeZone {
  return SAFE_ZONES[name ?? 'tiktok'] ?? SAFE_ZONES.tiktok
}

// ---- framing (gaming/framing.py) --------------------------------------------------------

export function camCrop(box: PxBox, head: Head | null, dest: PxBox, safe: SafeZone): [PxBox, number] {
  const [bx, by, bw, bh] = box
  const aspect = dest[2] / dest[3]
  let cw: number
  let ch: number
  if (bw / bh > aspect) {
    ch = bh
    cw = ch * aspect
  } else {
    cw = bw
    ch = cw / aspect
  }
  if (head === null) {
    const x = bx + (bw - cw) / 2
    const y = by + (bh - ch) / 2
    return [[pos(x), pos(y), even(cw), even(ch)], 0]
  }
  const [hx, top] = head
  const scale = dest[3] / ch
  const [, dy, , dh] = dest
  let wantTop = dy + HEADROOM * dh
  if (dy < safe.top) wantTop = Math.max(wantTop, safe.top)
  const x = clamp(hx - cw / 2, bx, bx + bw - cw)
  const y = clamp(top - (wantTop - dy) / scale, by, by + bh - ch)
  const lands = dy + (top - y) * scale
  const shift = roundHalfEven(Math.min(Math.max(0, wantTop - lands), MAX_SHIFT * dh))
  return [[pos(x), pos(y), even(cw), even(ch)], shift]
}

export function headOnCanvas(head: Head, crop: PxBox, dest: PxBox, shift: number): [number, number] {
  const [, top, chin] = head
  const scale = dest[3] / crop[3]
  return [dest[1] + shift + (top - crop[1]) * scale, dest[1] + shift + (chin - crop[1]) * scale]
}

export function faceClear(
  head: Head | null,
  crop: PxBox,
  dest: PxBox,
  shift: number,
  safe: SafeZone
): { top: boolean; bottom: boolean } {
  if (head === null) return { top: true, bottom: true }
  const [top, chin] = headOnCanvas(head, crop, dest, shift)
  return {
    top: top >= Math.max(dest[1], safe.top) - 1,
    bottom: chin <= Math.min(dest[1] + dest[3], OUT_H - safe.bottom) + 1
  }
}

// ---- layout (gaming/layout.py) -----------------------------------------------------------

function clampBox(box: FrameBox, srcW: number, srcH: number): PxBox {
  const [x, y, w, h] = box
  const x0 = Math.min(Math.max(0, x), 1) * srcW
  const y0 = Math.min(Math.max(0, y), 1) * srcH
  const x1 = Math.min(Math.max(x + w, 0), 1) * srcW
  const y1 = Math.min(Math.max(y + h, 0), 1) * srcH
  return [pos(x0), pos(y0), even(Math.max(2, x1 - x0)), even(Math.max(2, y1 - y0))]
}

function aligned(srcW: number, cropW: number, align: string): number {
  if (align === 'left') return 0
  if (align === 'right') return srcW - cropW
  return pos((srcW - cropW) / 2)
}

function clearOf(srcW: number, cropW: number, cams: PxBox[]): number {
  const centre = (srcW - cropW) / 2
  let best = 0
  let bestKey: [number, number] | null = null
  for (let x = 0; x <= srcW - cropW; x += 2) {
    let overlap = 0
    for (const c of cams) overlap += Math.max(0, Math.min(x + cropW, c[0] + c[2]) - Math.max(x, c[0]))
    const key: [number, number] = [overlap, Math.abs(x - centre)]
    if (bestKey === null || key[0] < bestKey[0] || (key[0] === bestKey[0] && key[1] < bestKey[1])) {
      best = x
      bestKey = key
    }
  }
  return best
}

function cover(box: PxBox, aspect: number): PxBox {
  const [x, y, w, h] = box
  if (w / h > aspect) {
    const cw = even(h * aspect)
    return [pos(x + (w - cw) / 2), y, cw, h]
  }
  const ch = even(w / aspect)
  return [x, pos(y + (h - ch) / 2), w, ch]
}

function shown(box: PxBox, aspect: number): number {
  const [, , w, h] = box
  const scale = Math.min(aspect / w, 1 / h)
  return w * h * scale * scale
}

function beside(srcW: number, srcH: number, cam: PxBox, aspect: number): PxBox {
  const [cx, cy, cw, ch] = cam
  const strips = (
    [
      [0, 0, cx, srcH],
      [cx + cw, 0, srcW - cx - cw, srcH],
      [0, 0, srcW, cy],
      [0, cy + ch, srcW, srcH - cy - ch]
    ] as PxBox[]
  ).filter((s) => s[2] >= 0.2 * srcW && s[3] >= 0.2 * srcH)
  if (strips.length === 0) return [0, 0, even(srcW), even(srcH)]
  let best = strips[0]
  for (const s of strips) if (shown(s, aspect) > shown(best, aspect)) best = s
  const [x, y, w, h] = best
  return [pos(x), pos(y), even(w), even(h)]
}

/** The preset that can actually be drawn with these settings (layout.resolve). */
export function resolve(settings: LayoutSettings): LayoutSettings & { preset: string } {
  const s: LayoutSettings = { ...settings }
  let preset = s.preset
  if (!preset || !(preset in PRESETS)) {
    preset = 'half'
    if (s.order === undefined) s.order = s.cam_position === 'bottom' ? 'game_top' : 'cam_top'
    if (s.game_fit === undefined) s.game_fit = s.game_fit || 'fit'
  }
  const spec = PRESETS[preset]
  const roles = new Set<string>([...(spec.rows ?? []).flat(), ...(spec.cams ?? [])])
  if (roles.has('cam') && !s.cam) preset = 'blurred'
  else if (roles.has('ui') && !s.ui_box) preset = 'split'
  else if (roles.has('cam2') && !s.cam2) preset = ({ dual_cam: 'small_cam', duo_split: 'split' } as Record<string, string>)[preset] ?? preset
  return { ...s, preset }
}

function stackRegions(spec: Spec, order: string, divider: number | undefined): [string, PxBox, Element['anchor']][] {
  const rows = (spec.rows ?? []).map((r) => [...r])
  if (order === 'game_top') rows.reverse()
  const [lo, hi, def] = spec.divider ?? [0.5, 0.5, 0.5]
  const camH = OUT_H * Math.min(Math.max(divider ?? def, lo), hi)
  let heights: (number | null)[] = rows.map((row) =>
    row.includes('game') ? null : row.includes('ui') && row.length === 1 ? OUT_H * (spec.ui_share ?? 0.12) : camH
  )
  const rest = OUT_H - heights.reduce<number>((a, h) => a + (h ?? 0), 0)
  heights = heights.map((h) => (h === null ? rest : h))
  const edges = [0]
  for (const h of heights.slice(0, -1)) edges.push(pos(edges[edges.length - 1] + (h as number)))
  edges.push(OUT_H)
  const out: [string, PxBox, Element['anchor']][] = []
  rows.forEach((row, i) => {
    const anchor: Element['anchor'] = i === 0 ? 'top' : i === rows.length - 1 ? 'bottom' : 'center'
    const cols = [...row.map((_, j) => pos((j * OUT_W) / row.length)), OUT_W]
    row.forEach((role, j) => {
      out.push([role, [cols[j], edges[i], cols[j + 1] - cols[j], edges[i + 1] - edges[i]], anchor])
    })
  })
  return out
}

function pipRegions(spec: Spec, safe: SafeZone): [string, PxBox][] {
  const cams = spec.cams ?? ['cam']
  const w = even(OUT_W * (spec.pip_width ?? 0.4))
  const h = even(w / (spec.pip_aspect ?? 1))
  const y = pos(safe.top + PIP_MARGIN * OUT_H)
  const total = cams.length * w + (cams.length - 1) * PIP_GAP
  const x0 = (OUT_W - total) / 2
  return cams.map((role, i) => [role, [pos(x0 + i * (w + PIP_GAP)), y, w, h]])
}

function gameSrc(srcW: number, srcH: number, s: LayoutSettings, dest: PxBox, fit: string, cams: PxBox[]): PxBox {
  const aspect = dest[2] / dest[3]
  if (s.game_box) {
    const region = clampBox(s.game_box, srcW, srcH)
    return fit === 'fit' ? region : cover(region, aspect)
  }
  if (fit === 'fit') return cams.length === 0 ? [0, 0, even(srcW), even(srcH)] : beside(srcW, srcH, cams[0], aspect)
  const cropW = Math.min(srcW, even(srcH * aspect))
  const align = ['left', 'center', 'right'].includes(s.game_align ?? '') ? (s.game_align as string) : 'center'
  const x = cams.length > 0 && align === 'center' ? clearOf(srcW, cropW, cams) : aligned(srcW, cropW, align)
  const cropH = cropW === srcW ? Math.min(srcH, even(cropW / aspect)) : even(srcH)
  return [pos(x), pos((srcH - cropH) / 2), cropW, cropH]
}

export function plan(
  srcW: number,
  srcH: number,
  settings: LayoutSettings,
  heads: Partial<Record<Role, Head>> = {}
): GamingPlan {
  const s = resolve(settings)
  const preset = s.preset
  const spec = PRESETS[preset]
  const order = (s.order === 'cam_top' || s.order === 'game_top' ? s.order : spec.order ?? 'cam_top') as
    | 'cam_top'
    | 'game_top'
  const safeName = s.safe && s.safe in SAFE_ZONES ? s.safe : 'tiktok'
  const safe = safeZone(safeName)
  // Blurred and Fullscreen ARE the game shown whole or zoomed: the layout decides.
  const fit =
    spec.type === 'full'
      ? (spec.game_fit as string)
      : s.game_fit === 'fit' || s.game_fit === 'fill'
        ? s.game_fit
        : spec.game_fit ?? 'fill'
  const camBoxes: Partial<Record<Role, PxBox>> = {}
  for (const role of ['cam', 'cam2'] as const) {
    const box = s[role]
    if (box) camBoxes[role] = clampBox(box, srcW, srcH)
  }
  const shownCams = (['cam', 'cam2'] as const).filter((r) => camBoxes[r]).map((r) => camBoxes[r] as PxBox)
  const elements: Element[] = []

  const camera = (role: Role, dest: PxBox, shape: Element['shape'] = 'rect'): void => {
    const [crop, shift] = camCrop(camBoxes[role] as PxBox, heads[role] ?? null, dest, safe)
    elements.push({ role, src: crop, dest, fit: 'cover', anchor: 'center', shift, shape })
  }
  const game = (dest: PxBox, anchor: Element['anchor']): void => {
    const src = gameSrc(srcW, srcH, s, dest, fit, shownCams)
    elements.push({ role: 'game', src, dest, fit: fit === 'fit' ? 'contain' : 'cover', anchor, shift: 0, shape: 'rect' })
  }

  if (spec.type === 'full') {
    game([0, 0, OUT_W, OUT_H], 'center')
  } else if (spec.type === 'pip') {
    game([0, 0, OUT_W, OUT_H], 'center')
    for (const [role, dest] of pipRegions(spec, safe)) camera(role as Role, dest, (spec.shape ?? 'rect') as Element['shape'])
  } else {
    for (const [role, dest, anchor] of stackRegions(spec, order, s.divider)) {
      if (role === 'game') game(dest, anchor)
      else if (role === 'ui') {
        const ui = clampBox(s.ui_box as FrameBox, srcW, srcH)
        elements.push({ role: 'ui', src: ui, dest, fit: 'contain', anchor: 'center', shift: 0, shape: 'rect' })
      } else camera(role as Role, dest)
    }
  }
  return { preset, elements, order, safe: safeName }
}

/** The element for a role, if the plan has one. */
export const elementOf = (p: GamingPlan, role: Role): Element | undefined => p.elements.find((e) => e.role === role)
