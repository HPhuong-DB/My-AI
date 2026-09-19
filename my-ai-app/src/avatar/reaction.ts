/** Conservative presentation policy for the final assistant text, not the user's mood.
 * Raw model motion/expression names are intentionally not trusted as visual directions.
 */
export type ReactionKind = 'neutral' | 'warm' | 'celebrate' | 'comfort' | 'curious' | 'goodnight';
export interface ReactionPlan {
  text: string;
  kind: ReactionKind;
  expression: '' | 'warm' | 'baozhen';
  motion: '' | 'qizi' | 'haoqi' | 'keshui';
  displayMs: number;
  holdMs: number;
}

export function readingDuration(text: string): number {
  const units = text.trim().split(/\s+/u).filter(Boolean).length;
  const pauses = (text.match(/[.!?;\n]/gu) || []).length;
  return Math.min(30_000, Math.max(4000, Math.round(1600 + units * 220 + pauses * 120)));
}

export function planReaction(text: string): ReactionPlan {
  const displayMs = readingDuration(text);
  const plan: ReactionPlan = { text, kind: 'neutral', expression: '', motion: '', displayMs, holdMs: 0 };
  const prose = text.replace(/```[\s\S]*?```|`[^`]*`|“[^”]*”|"[^"]*"|'[^']*'/gu, ' ')
    .normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/giu, 'd').toLowerCase();
  // Explaining or quoting an emotion is not expressing it.
  if (/```|`/.test(text) || /\b(khai niem|dinh nghia|vi du|thuat toan|cu phap)\b/u.test(prose)
    || /\b(?:buon|vui|tuc gian) la (?:mot |cam giac|trang thai)/u.test(prose)) return plan;
  const current = prose.replace(/\bkhong (?:con )?(?:buon|met|lo lang|that vong)(?: nua)?\b/gu, '')
    .replace(/\b(?:khong|dung|chua)(?: nen| voi| can)? chuc mung\b/gu, '');
  if (/\b(rat tiec|tiec qua|buon|that vong|mat (?:het )?bai|khong vui|khong on|khong thanh cong|minh nghe|to nghe|cu ke)\b/u.test(current)) {
    Object.assign(plan, { kind: 'comfort', expression: 'baozhen', holdMs: 6000 });
  } else if (/\b(ngu ngon|nghi ngoi nhe)\b/u.test(current)) {
    Object.assign(plan, { kind: 'goodnight', expression: 'warm', motion: 'keshui', holdMs: 5900 });
  } else if (/\b(chuc mung|lam duoc roi|sua duoc roi|hoan thanh roi|mung cho (?:ban|cau))\b/u.test(current)) {
    Object.assign(plan, { kind: 'celebrate', expression: 'warm', motion: 'qizi', holdMs: 8000 });
  } else if (/\b(to mo|ke them|o dau|the nao)\b/u.test(current) && current.includes('?')) {
    Object.assign(plan, { kind: 'curious', motion: 'haoqi', holdMs: 4567 });
  } else if (/\b(chao|cam on|hen gap lai|rat vui)\b/u.test(current)) {
    Object.assign(plan, { kind: 'warm', expression: 'warm', holdMs: 3500 });
  }
  plan.holdMs = Math.min(plan.holdMs, displayMs);
  return plan;
}
