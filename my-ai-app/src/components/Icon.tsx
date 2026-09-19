import type { SVGProps } from 'react';
const paths = {
  mic: <><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></>,
  send: <><path d="m5 12 7-7 7 7M12 5v15"/></>,
  tools: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  window: <><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 8h18M14 12h4v5h-4z"/></>,
  stop: <rect x="6" y="6" width="12" height="12" rx="2"/>,
};
export function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: keyof typeof paths }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>;
}
