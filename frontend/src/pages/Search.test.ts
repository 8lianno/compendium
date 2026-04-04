import { fireEvent, render, screen } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Search from "./Search.svelte";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({
  api: {
    search: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

describe("Search", () => {
  beforeEach(() => {
    mockedApi.search.mockReset();
  });

  it("renders highlighted results and opens the selected article", async () => {
    const onOpenArticle = vi.fn();
    mockedApi.search.mockResolvedValue({
      query: "climate",
      results: [
        {
          path: "wiki/research/climate.md",
          title: "Climate research digest",
          category: "research",
          score: 0.98,
          snippet: "Climate signals are increasing across regions.",
        },
      ],
    });

    render(Search, { props: { onOpenArticle } });

    const input = screen.getByPlaceholderText(
      "Search wiki articles, concepts, and notes...",
    ) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "climate" } });
    await new Promise((resolve) => setTimeout(resolve, 250));

    expect(mockedApi.search).toHaveBeenCalledWith("climate", 12);

    const matches = await screen.findAllByText("Climate", { selector: "mark" });
    expect(matches).toHaveLength(2);

    await fireEvent.click(screen.getByRole("button", { name: /Climate research digest/i }));
    expect(onOpenArticle).toHaveBeenCalledWith("wiki/research/climate.md");
  });
});
