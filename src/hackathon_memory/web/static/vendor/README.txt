The files of other projects that the website serves, as they were published on the npm registry.
Each package was checked against the registry's own sha512 before its files were taken.

htmx.min.js                 htmx.org 2.0.11, license 0BSD (htmx-LICENSE.txt)
tabler.min.css              @tabler/core 1.6.1, the design system of the page, built on
tabler-themes.min.css       Bootstrap 5; license MIT (the notice is at the top of each file)
chart.umd.js                chart.js 4.5.1, the charts; license MIT (chart-LICENSE.md)
ibm-plex-sans-*.woff2       @fontsource/ibm-plex-sans 5.3.0, latin subset, weights 400 to 700,
                            SIL Open Font License 1.1 (ibm-plex-sans-LICENSE.txt)
atkinson-mono-400.woff2     @fontsource/atkinson-hyperlegible-mono 5.3.0, latin subset,
                            SIL Open Font License 1.1 (atkinson-mono-LICENSE.txt), for the IDs

The page uses Tabler's own components (cards, badges, buttons, tables, alerts, pagination,
placeholders) with its theme "teal" on the base "stone". It does not load Tabler's script: the
windows are the browser's own dialog and popover elements, and htmx loads the parts of the page.
