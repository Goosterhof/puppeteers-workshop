import {defineConfig, presetWind3, transformerVariantGroup} from 'unocss';

// The Prompter's Box — booth palette as tokens (#00063 Phase 1).
//
// The preflight carries the old front's `:root` custom properties 1:1 so the
// ported component CSS keeps reading `var(--lamp)` etc. — pixel fidelity is
// the acceptance contract, not a redesign. The theme mirrors the same values
// so Uno utilities (text-lamp, bg-drape, …) resolve to identical hexes when
// later phases reach for them.
//
// The reduced-motion floor rides the preflight — the canonical gadget shape
// (gadgets/mezzanine/uno.config.ts is the reference). The Potter's Wheel keeps
// its own renderer-side matchMedia gate on top of this CSS surface.

export default defineConfig({
    presets: [presetWind3({dark: 'class'})],
    transformers: [transformerVariantGroup()],
    theme: {
        colors: {
            booth: '#17130f',
            drape: '#241d16',
            'drape-edge': '#33291d',
            lamp: '#e8b04a',
            'lamp-dim': '#8a6a2e',
            paper: '#efe6d2',
            'paper-shade': '#e0d4ba',
            ink: '#2b241b',
            dim: '#9a8b74',
            'cue-red': '#c2543a',
            'go-green': '#7da16b',
            'stage-off': '#241c14',
            'stage-dead': '#17130f',
            filament: '#ffd27a',
            'plate-face': '#1d1610',
            'plate-edge': '#3a2e1f',
            'meter-well': '#0d0b08',
            ember: '#cc6b33',
            'ember-dim': '#7a4322',
            cured: '#7da16b',
            tattered: '#c2543a',
            curing: '#8a6a2e',
        },
        fontFamily: {
            display: "'Oswald', 'Arial Narrow', 'Helvetica Neue', sans-serif",
            body: "system-ui, 'Segoe UI', sans-serif",
            typed: "'Courier Prime', 'Courier New', monospace",
        },
    },
    preflights: [
        {
            getCSS: () => `
        :root {
          --booth: #17130f;
          --drape: #241d16;
          --drape-edge: #33291d;
          --lamp: #e8b04a;
          --lamp-dim: #8a6a2e;
          --paper: #efe6d2;
          --paper-shade: #e0d4ba;
          --ink: #2b241b;
          --dim: #9a8b74;
          --cue-red: #c2543a;
          --go-green: #7da16b;
          --stage-off: #241c14;   /* lamp present but unlit */
          --stage-dead: #17130f;  /* lost-contact */
          --filament: #ffd27a;    /* hot core, live only */
          --plate-face: #1d1610;
          --plate-edge: #3a2e1f;
          --meter-well: #0d0b08;
          --display: 'Oswald', 'Arial Narrow', 'Helvetica Neue', sans-serif;
          --body: system-ui, 'Segoe UI', sans-serif;
          --typed: 'Courier Prime', 'Courier New', monospace;
          /* the kiln's sub-dialect: heat that healed */
          --ember:     #cc6b33;   /* the kiln's healed scar — refired-and-recovered, warm not alarming */
          --ember-dim: #7a4322;   /* scar-chip ground/border */
          --cured:     #7da16b;   /* QA passed  — semantic alias of --go-green */
          --tattered:  #c2543a;   /* QA failed / still shredding — alias of --cue-red */
          --curing:    #8a6a2e;   /* QA pending — alias of --lamp-dim */
        }
        * { box-sizing: border-box; margin: 0; }
        body {
          background: var(--booth);
          background-image: radial-gradient(ellipse 900px 340px at 50% -80px, rgba(232,176,74,.14), transparent 70%);
          color: var(--dim);
          font-family: var(--body);
          font-size: 15px;
          line-height: 1.5;
          min-height: 100vh;
        }
        main { max-width: 1680px; margin: 0 auto; padding: 0 20px 80px; }
        /* the amber wash while a take runs — the mutex felt page-wide */
        body.take-running { background-image: radial-gradient(ellipse 900px 340px at 50% -80px, rgba(232,176,74,.24), transparent 70%); }

        /* ---- shared booth grammar: panels, fields, pills, the fire button ---- */
        .panel { background: var(--drape); border: 1px solid var(--drape-edge); border-radius: 3px; padding: 22px; }
        label.field { display: block; font-size: 11px; letter-spacing: .16em; text-transform: uppercase; margin: 14px 0 5px; }
        /* text/number/textarea/select controls are ui-inputs atoms now — their
           chrome lives on the --ui-* contract in src/ui-inputs-map.css; only
           the native holdouts (checkboxes) and buttons keep element rules */
        input[type=checkbox]:focus, button:focus-visible { outline: 2px solid var(--lamp-dim); outline-offset: 1px; }
        .row { display: flex; gap: 14px; flex-wrap: wrap; align-items: flex-end; }
        .row > div { flex: 1; min-width: 110px; }
        .pills { display: flex; gap: 6px; flex-wrap: wrap; }
        .pills button {
          background: var(--booth); border: 1px solid var(--drape-edge); color: var(--dim);
          font: 12px var(--display); letter-spacing: .16em; text-transform: uppercase;
          padding: 7px 14px; cursor: pointer; border-radius: 2px;
        }
        .pills button[aria-pressed="true"] { border-color: var(--lamp); color: var(--lamp); }
        .fire {
          background: var(--lamp); border: none; color: var(--ink);
          font: 600 13px var(--display); letter-spacing: .2em; text-transform: uppercase;
          padding: 11px 26px; cursor: pointer; border-radius: 2px; margin-top: 18px;
        }
        .fire:hover { filter: brightness(1.08); }
        .fire:disabled { background: var(--lamp-dim); cursor: wait; }
        .fire.danger { background: var(--tattered); color: var(--paper); }
        .note { font-size: 12px; margin-top: 10px; }
        .note a { color: var(--lamp); }
        .error { color: var(--cue-red); font-size: 13px; margin-top: 12px; white-space: pre-wrap; }
        .empty { font-size: 12px; font-style: italic; color: var(--dim); letter-spacing: .06em; }
        .result { margin-top: 18px; display: grid; gap: 16px; justify-items: start; }
        .result .cap { font-size: 12px; letter-spacing: .08em; }
        .thumbrow { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 6px; }
        .thumbrow img, .thumbrow video {
          height: 86px; border: 2px solid transparent; border-radius: 2px; cursor: pointer;
          opacity: .75;
        }
        .thumbrow img:hover, .thumbrow video:hover { opacity: 1; }
        .thumbrow img.picked { border-color: var(--lamp); opacity: 1; }

        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after {
            animation-duration: .01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: .01ms !important;
            scroll-behavior: auto !important;
          }
        }
      `,
        },
    ],
});
