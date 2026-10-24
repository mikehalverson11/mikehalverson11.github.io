// Renders digest.json into #digest. Uses DOM APIs (no innerHTML), so text from
// outside APIs can never inject markup.
(function () {
  const root = document.getElementById("digest");
  const stamp = document.getElementById("digest-updated");

  function safeUrl(u) {
    try {
      const url = new URL(u, location.href);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
    } catch (e) { return null; }
  }

  function fill(el, parts) {
    for (const p of parts) {
      const href = p.url ? safeUrl(p.url) : (/^https?:\/\/\S+$/.test(p.text.trim()) ? safeUrl(p.text.trim()) : null);
      if (href) {
        const a = document.createElement("a");
        a.href = href; a.textContent = p.text; a.rel = "noopener"; a.target = "_blank";
        el.appendChild(a);
      } else {
        el.appendChild(document.createTextNode(p.text));
      }
    }
  }

  function render(data) {
    root.textContent = "";
    let list = null;
    for (const b of data.blocks) {
      if (b.type !== "bullet") list = null;
      if (b.type === "heading") {
        const h = document.createElement("h2"); fill(h, b.parts); root.appendChild(h);
      } else if (b.type === "paragraph") {
        const p = document.createElement("p"); fill(p, b.parts); root.appendChild(p);
      } else if (b.type === "bullet") {
        if (!list) { list = document.createElement("ul"); root.appendChild(list); }
        const li = document.createElement("li"); fill(li, b.parts); list.appendChild(li);
      } else if (b.type === "todo") {
        const row = document.createElement("div");
        const box = document.createElement("input");
        box.type = "checkbox"; box.disabled = true;
        const label = document.createElement("span"); fill(label, b.parts);
        row.appendChild(box); row.appendChild(document.createTextNode(" ")); row.appendChild(label);
        root.appendChild(row);
      } else if (b.type === "divider") {
        root.appendChild(document.createElement("hr"));
      } else if (b.type === "image") {
        const href = safeUrl(b.url);
        if (href) {
          const img = document.createElement("img");
          img.src = href; img.alt = ""; img.loading = "lazy"; root.appendChild(img);
        }
      }
    }
    if (stamp && data.generated) {
      stamp.textContent = "Last updated " + new Date(data.generated).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    }
  }

  fetch("digest.json", { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(render)
    .catch(() => { root.textContent = "The digest isn't available yet. It's built each morning by a GitHub Action."; });
})();
