<script lang="ts">
  import { marked } from "marked";

  interface Props {
    source: string;
  }

  let { source }: Props = $props();

  // Configure marked for wikilinks
  const renderer = new marked.Renderer();
  const originalLink = renderer.link.bind(renderer);
  renderer.link = ({ href, title, text }) => {
    // Convert [[wikilinks]] that marked might parse
    return originalLink({ href, title, text });
  };

  marked.setOptions({ renderer, breaks: true, gfm: true });

  let html = $derived(
    // Pre-process: convert [[wikilinks]] to clickable spans
    marked.parse(
      source.replace(
        /\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]/g,
        (_, target, display) =>
          `<a class="wikilink" href="#" data-target="${target}">${display || target}</a>`
      )
    ) as string
  );
</script>

<div class="markdown">
  {@html html}
</div>
