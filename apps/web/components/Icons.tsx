const paths = {
  arrow: <path d="M4.5 12h15M13.5 6l6 6-6 6" />,
  back: <path d="M19.5 12h-15M10.5 6l-6 6 6 6" />,
  attach: <path d="M20 11.2 12.1 19a5 5 0 0 1-7.1-7.1l8.5-8.4a3.4 3.4 0 0 1 4.8 4.8l-8.4 8.4a1.8 1.8 0 0 1-2.6-2.6l7.7-7.6" />,
  lock: <><rect x="5" y="10.5" width="14" height="10" rx="2.5" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></>,
  info: <><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5.5M12 7.6v.2" /></>,
  download: <path d="M12 4v11M7 10.5l5 5 5-5M5 20h14" />,
  globe: <><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.6 2.4 3.9 5.2 3.9 8.5s-1.3 6.1-3.9 8.5c-2.6-2.4-3.9-5.2-3.9-8.5S9.4 5.9 12 3.5z" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
  book: <><path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v15H7.5A2.5 2.5 0 0 0 5 20.5v-15z" /><path d="M5 20.5A2.5 2.5 0 0 1 7.5 18H19v3H7.5" /></>,
  pen: <><path d="M4 20h4.2L19.4 8.8a2 2 0 0 0 0-2.8l-1.4-1.4a2 2 0 0 0-2.8 0L4 15.8V20z" /><path d="M13.5 6.5l4 4" /></>,
  trash: <path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5" />,
  bolt: <path d="M13 3 5.5 13.5H11L10 21l7.5-10.5H12L13 3z" />,
  layers: <><path d="m12 3.5 8.5 4.75L12 13 3.5 8.25 12 3.5z" /><path d="m3.5 12.5 8.5 4.75 8.5-4.75" /></>,
  question: <><circle cx="12" cy="12" r="8.5" /><path d="M9.6 9.4a2.5 2.5 0 1 1 3.6 2.3c-.8.4-1.2 1-1.2 1.8v.6M12 16.8v.2" /></>,
  bulb: <path d="M9.5 17.5h5M10.5 21h3M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.1v1.6h5v-1.6c0-.8.4-1.6 1.1-2.1A6 6 0 0 0 12 3z" />,
  close: <path d="m5 5 14 14M19 5 5 19" />,
};
export type IconName = keyof typeof paths;

export function Icon({ name }: { name: IconName }) {
  return <svg className="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor"
    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}
