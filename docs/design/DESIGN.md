# Quick check

The home page puts a two-line question above a single writing surface. The dial in “robot” uses the same needle and chartreuse face as the wordmark. Desktop content stays within 1,200 px, and the editor fits in the first 1280 × 800 viewport. At narrow widths the input tools wrap and the signal cards become one column.

Use paper `#FAF8F4` for the canvas, ink `#171512` for text, lavender `#E9E6F2` for the editor and verdict, and chartreuse `#D8FF3E` for action fills and the interval arc. Text, numeric labels and line weights carry the meaning alongside colour. Cards use a 24 px radius. Active controls have visible keyboard focus.

Clash Display Semibold comes from Fontshare. The development and build commands fetch a digest-verified copy directly from the foundry and serve it locally. Instrument Sans, JetBrains Mono and Noto Sans HK are self-hosted Fontsource assets. Use Clash for headlines, Instrument Sans for prose and JetBrains Mono for measurements and counters. [Fontshare licence](https://www.fontshare.com/licenses/itf-ffl)

English and Traditional Chinese strings live in the message catalogues. The English interface lives at `/` and Hong Kong Chinese at `/zh-HK`. Both accept English essays of 150–5,000 words. File import extracts plain text in the browser. An accessible status line describes progress and refusals.

The verdict shows the index, band, calibration interval and two keyboard-accessible explanation dialogs. Each signal shows a measured value and the corresponding median from human training essays. A sparkline appears when the engine supplies multiple samples. The gauge needle settles once. With reduced motion, it displays the final reading immediately.

A successful check stores the submitted essay, result and claim token in IndexedDB. The browser discards expired checks on the next access after 30 days. “Forget on this device” clears the local check store. The API receives the essay for in-memory analysis. It returns scores without the essay.

The browser smoke suite builds and starts Next.js, exercises the checks route through local mock upstreams, and runs axe on the input, results and dialogs. It also covers a file upload, reduced motion, refusal recovery, local erasure and the narrow Hong Kong Chinese layout.
