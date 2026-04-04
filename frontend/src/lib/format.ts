export function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function highlightText(text: string, query: string): string {
  if (!query.trim()) {
    return escapeHtml(text);
  }

  const terms = query
    .trim()
    .split(/\s+/)
    .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .filter(Boolean);

  if (terms.length === 0) {
    return escapeHtml(text);
  }

  const pattern = new RegExp(`(${terms.join("|")})`, "gi");
  return escapeHtml(text).replace(pattern, "<mark>$1</mark>");
}

export function toProjectRelativePath(path: string | undefined | null): string | null {
  if (!path) {
    return null;
  }
  if (!path.startsWith("/")) {
    return path.replace(/^\.?\//, "");
  }

  const match = path.match(/\/(wiki|raw|output)\/.+$/);
  return match ? match[0].slice(1) : null;
}

export function formatContextWindow(value: number | null | undefined): string {
  if (!value) {
    return "Unknown";
  }
  return new Intl.NumberFormat().format(value);
}

export function formatPricing(pricing: {
  input_per_million: number;
  output_per_million: number;
} | null): string {
  if (!pricing) {
    return "Pricing unavailable";
  }
  return `$${pricing.input_per_million.toFixed(2)} in / $${pricing.output_per_million.toFixed(
    2,
  )} out per 1M tokens`;
}
