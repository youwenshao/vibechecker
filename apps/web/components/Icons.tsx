const paths = {
  arrow: "M4 12h15m-6-6 6 6-6 6",
  attach: "m8 15 7.4-7.4a2.4 2.4 0 0 1 3.4 3.4L9.2 20.6a5 5 0 0 1-7.1-7.1l10-10",
  lock: "M7 10V7a5 5 0 0 1 10 0v3M5 10h14v11H5zM12 14v3",
  bolt: "m13 2-9 12h7l-1 8 10-13h-8z",
  close: "m5 5 14 14M19 5 5 19",
  erase: "M3 6h18M8 6V3h8v3M6 6l1 15h10l1-15M10 10v7m4-7v7",
  pencil: "m4 16 11-11 4 4L8 20l-5 1zM13 7l4 4",
  globe: "M2 12h20M12 2c-6 6-6 14 0 20 6-6 6-14 0-20z",
} as const;
export function Icon({ name }: { name: keyof typeof paths }) {
  return <svg viewBox="0 0 24 24" className="icon" aria-hidden="true" fill="none" stroke="currentColor"
    strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
    {name === "globe" && <circle cx="12" cy="12" r="10" />}
    <path d={paths[name]} />
  </svg>;
}

export function Dial({ glyph }: { glyph?: boolean }) {
  return <span className={glyph ? "dial glyph" : "dial"} aria-hidden="true">
    <svg viewBox="0 0 48 48" fill="none">
      <path d="M10 29a15 15 0 0 1 28 0" stroke="currentColor" strokeWidth="3.5" />
      <path d="m12.5 19.5 4.2 2.6M23.5 13v5M34.7 18.1l-3.3 3.8" stroke="currentColor" strokeWidth="2.4" />
      <g className="dial-needle"><path d="m24 31 9-13" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round"/>
        <circle cx="24" cy="31" r="3.4" fill="currentColor"/></g>
    </svg>
  </span>;
}
