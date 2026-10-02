// Tiny, safe Markdown → HTML renderer for knowledgebase articles. Escapes all HTML
// first, then applies a small, well-known subset (headings, bold/italic, inline code,
// links, ordered/unordered lists, blockquotes, paragraphs). Content is author-trusted
// (managers only) but we escape anyway so nothing can inject markup.

function esc(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] as string);
}

type Resolve = (url: string) => string;

function inline(s: string, resolve: Resolve): string {
  let out = esc(s);
  // Images first (so the link rule below doesn't swallow the ![alt](url) form).
  out = out.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_m, alt: string, url: string) => {
    const safe = resolve(url).replace(/"/g, "&quot;");
    return `<img src="${safe}" alt="${alt}" loading="lazy"/>`;
  });
  out = out.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  return out;
}

export function renderMarkdown(md: string, resolveSrc: Resolve = (u) => u): string {
  const inl = (s: string) => inline(s, resolveSrc);
  const lines = (md || "").replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let i = 0;
  let para: string[] = [];

  const flushPara = () => {
    if (para.length) {
      html.push(`<p>${para.map(inl).join("<br/>")}</p>`);
      para = [];
    }
  };

  while (i < lines.length) {
    const raw = lines[i];
    const line = raw.trimEnd();

    if (!line.trim()) {
      flushPara();
      i++;
      continue;
    }

    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flushPara();
      const lvl = h[1].length;
      html.push(`<h${lvl}>${inl(h[2])}</h${lvl}>`);
      i++;
      continue;
    }

    if (/^>\s?/.test(line)) {
      flushPara();
      const quote: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        quote.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      html.push(`<blockquote>${quote.map(inl).join("<br/>")}</blockquote>`);
      continue;
    }

    const isUl = /^[-*]\s+/.test(line);
    const isOl = /^\d+\.\s+/.test(line);
    if (isUl || isOl) {
      flushPara();
      const tag = isUl ? "ul" : "ol";
      const items: string[] = [];
      while (i < lines.length) {
        const l = lines[i];
        const m = l.match(isUl ? /^[-*]\s+(.*)$/ : /^\d+\.\s+(.*)$/);
        if (m) {
          items.push(inl(m[1].trimEnd()));
          i++;
        } else if (/^\s+\S/.test(l) && items.length) {
          // continuation line indented under the current item
          items[items.length - 1] += "<br/>" + inl(l.trim());
          i++;
        } else {
          break;
        }
      }
      html.push(`<${tag}>${items.map((it) => `<li>${it}</li>`).join("")}</${tag}>`);
      continue;
    }

    para.push(line);
    i++;
  }
  flushPara();
  return html.join("\n");
}
