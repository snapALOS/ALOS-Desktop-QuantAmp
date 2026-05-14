/**
 * Maps kebab-case icon name strings (from MODULE.toml / Rust registry) to
 * lucide-react component references.
 *
 * RFC-0001 Decision 5: icons are strings; the frontend resolves them here.
 * Unknown names render CircleQuestionMark and log a warning.
 */

import {
  Activity,
  Code,
  FlaskConical,
  MessageSquare,
  Network,
  Puzzle,
  Settings,
  Workflow,
  CircleQuestionMark,
  TriangleAlert,
  Shield,
  Database,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

const iconMap: Record<string, LucideIcon> = {
  'activity': Activity,
  'code': Code,
  'flask-conical': FlaskConical,
  'message-square': MessageSquare,
  'network': Network,
  'puzzle': Puzzle,
  'settings': Settings,
  'workflow': Workflow,
  'triangle-alert': TriangleAlert,
  'shield': Shield,
  'database': Database,
  'circle-question-mark': CircleQuestionMark,
}

/**
 * Resolve a kebab-case icon name to a lucide-react component.
 * Returns CircleQuestionMark for unrecognised names.
 */
export function resolveIcon(name: string): LucideIcon {
  const icon = iconMap[name]
  if (!icon) {
    console.warn(`[icon-map] Unknown icon name "${name}", using fallback`)
    return CircleQuestionMark
  }
  return icon
}
