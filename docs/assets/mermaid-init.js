// Mermaid 11.x startOnLoad listens for DOMContentLoaded, but the script
// loads at the bottom of <body> so that event may have already fired.
// Explicitly run mermaid on all .mermaid divs.
if (typeof mermaid !== "undefined") {
  mermaid.initialize({ startOnLoad: false, theme: "default" });
  mermaid.run({ querySelector: ".mermaid" });
}
