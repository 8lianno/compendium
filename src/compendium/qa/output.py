"""Output rendering — markdown reports, Marp slides, matplotlib charts."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import frontmatter

if TYPE_CHECKING:
    from pathlib import Path


def render_report(
    query: str,
    answer: str,
    sources_used: list[str],
    tokens_used: int,
    output_dir: Path,
) -> Path:
    """Render a Q&A answer as a structured markdown report.

    Returns the path to the generated report file.
    """
    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")
    slug = re.sub(r"[^\w\s-]", "", query.lower()[:60])
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")

    fm_data = {
        "title": f"Report: {query[:80]}",
        "type": "report",
        "query": query,
        "generated_at": now.isoformat(),
        "sources_used": sources_used,
        "tokens_used": tokens_used,
        "filed_to_wiki": False,
    }

    body = f"# {query}\n\n"
    body += f"*Generated: {date_str}*\n\n"
    body += "## Answer\n\n"
    body += answer + "\n\n"
    body += "## Sources Consulted\n\n"
    for source in sources_used:
        body += f"- [[{source}]]\n"

    post = frontmatter.Post(body, **fm_data)

    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    output_path = reports_dir / f"{date_str}-{slug}.md"
    counter = 2
    while output_path.exists():
        output_path = reports_dir / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    output_path.write_text(frontmatter.dumps(post))
    return output_path


def render_slides(
    query: str,
    answer: str,
    sources_used: list[str],
    output_dir: Path,
    slide_count: int = 10,
) -> Path:
    """Render a Q&A answer as a Marp slide deck.

    Creates a Marp-compatible markdown file with --- slide separators.
    Returns the path to the generated slide file.
    """
    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")
    slug = re.sub(r"[^\w\s-]", "", query.lower()[:60])
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")

    # Split answer into logical sections for slides
    sections = _split_into_sections(answer, slide_count)

    lines = [
        "---",
        "marp: true",
        "theme: default",
        "paginate: true",
        f"title: {query[:80]}",
        "---",
        "",
        f"# {query[:80]}",
        "",
        f"*{date_str}*",
        "",
    ]

    for i, section in enumerate(sections):
        lines.append("---")
        lines.append("")
        if section["heading"]:
            lines.append(f"## {section['heading']}")
            lines.append("")
        lines.append(section["content"])
        lines.append("")
        # Speaker notes
        lines.append(f"<!-- Slide {i + 2} of {len(sections) + 2} -->")
        lines.append("")

    # Sources slide
    lines.append("---")
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for source in sources_used:
        lines.append(f"- {source}")
    lines.append("")

    content = "\n".join(lines)

    slides_dir = output_dir / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)

    output_path = slides_dir / f"{date_str}-{slug}.md"
    counter = 2
    while output_path.exists():
        output_path = slides_dir / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    output_path.write_text(content)
    return output_path


def _split_into_sections(text: str, target_count: int) -> list[dict[str, str]]:
    """Split text into sections suitable for slides."""
    # Try to split by markdown headings first
    heading_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    parts = heading_pattern.split(text)

    sections: list[dict[str, str]] = []

    if len(parts) > 1:
        # parts alternates: [pre-heading-text, heading1, content1, heading2, content2, ...]
        if parts[0].strip():
            sections.append({"heading": "Overview", "content": parts[0].strip()})
        for i in range(1, len(parts) - 1, 2):
            heading = parts[i].strip()
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if content:
                sections.append({"heading": heading, "content": content})
    else:
        # No headings — split by paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        # Group paragraphs to roughly target_count slides
        per_slide = max(1, len(paragraphs) // max(1, target_count))
        for i in range(0, len(paragraphs), per_slide):
            chunk = paragraphs[i : i + per_slide]
            sections.append(
                {
                    "heading": "",
                    "content": "\n\n".join(chunk),
                }
            )

    # Trim to target count
    return sections[:target_count]


def render_chart(
    title: str,
    data: dict[str, float],
    output_dir: Path,
    chart_type: str = "bar",
) -> Path | None:
    """Render a simple chart using matplotlib.

    Returns the path to the generated PNG, or None if matplotlib unavailable.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "bar":
        ax.bar(list(data.keys()), list(data.values()))
    elif chart_type == "pie":
        ax.pie(list(data.values()), labels=list(data.keys()), autopct="%1.1f%%")
    else:
        ax.plot(list(data.keys()), list(data.values()), marker="o")

    ax.set_title(title)
    fig.tight_layout()

    slug = re.sub(r"[^\w\s-]", "", title.lower()[:60])
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    output_path = charts_dir / f"{slug}.png"

    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def render_canvas(
    query: str,
    answer: str,
    sources_used: list[str],
    output_dir: Path,
) -> Path:
    """Render a Q&A answer as a Mermaid diagram / Obsidian Canvas.

    Creates a markdown file with embedded Mermaid diagram showing
    concept relationships extracted from the answer.
    Returns path to the generated file.
    """
    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")
    slug = re.sub(r"[^\w\s-]", "", query.lower()[:60])
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")

    # Extract concept mentions from answer (simple heuristic: [[wikilinks]])
    import re as _re

    wikilinks = _re.findall(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]", answer)
    unique_concepts = list(dict.fromkeys(wikilinks))[:20]

    # Build Mermaid flowchart
    mermaid_lines = ["```mermaid", "graph TD"]
    for i, concept in enumerate(unique_concepts):
        node_id = f"N{i}"
        label = concept.replace('"', "'")
        mermaid_lines.append(f'    {node_id}["{label}"]')

    # Connect sequential concepts (simple chain)
    for i in range(len(unique_concepts) - 1):
        mermaid_lines.append(f"    N{i} --> N{i + 1}")

    # Connect first and last to show cyclic relationship if > 3
    if len(unique_concepts) > 3:
        mermaid_lines.append(f"    N{len(unique_concepts) - 1} -.-> N0")

    mermaid_lines.append("```")

    body = f"# {query}\n\n"
    body += f"*Generated: {date_str}*\n\n"
    body += "## Concept Map\n\n"
    body += "\n".join(mermaid_lines) + "\n\n"
    body += "## Answer\n\n"
    body += answer + "\n\n"
    body += "## Sources\n\n"
    for source in sources_used:
        body += f"- [[{source}]]\n"

    charts_dir = output_dir / "diagrams"
    charts_dir.mkdir(parents=True, exist_ok=True)

    output_path = charts_dir / f"{date_str}-{slug}.md"
    counter = 2
    while output_path.exists():
        output_path = charts_dir / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    output_path.write_text(body)
    return output_path
