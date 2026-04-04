import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import Outputs from "./Outputs.svelte";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({
  api: {
    ask: vi.fn(),
    downloadUrl: vi.fn((path: string) => `/api/download/${path}`),
    fileToWiki: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

describe("Outputs", () => {
  it("shows filing actions for rendered outputs and files them back into the wiki", async () => {
    const onContentChanged = vi.fn();
    const onOpenArticle = vi.fn();

    mockedApi.ask.mockResolvedValue({
      answer: "## Competitive summary",
      sources_used: ["wiki/companies/example.md"],
      tokens_used: 321,
      articles_loaded: 4,
      output: "report",
      output_path: "output/report.md",
      extra_paths: [],
    });

    mockedApi.fileToWiki.mockResolvedValue({
      status: "filed",
      message: "Filed into wiki.",
      filed_path: "/Users/ali/personal/compendium/wiki/outputs/report.md",
    });

    render(Outputs, { props: { onContentChanged, onOpenArticle } });

    const question = screen.getByLabelText("Question");
    await fireEvent.input(question, { target: { value: "Summarize the latest competitor movement" } });

    const outputSelect = screen.getByLabelText("Output");
    await fireEvent.change(outputSelect, { target: { value: "report" } });

    await fireEvent.click(screen.getByRole("button", { name: "Generate output" }));

    expect(await screen.findByText("File output")).toBeInTheDocument();
    expect(mockedApi.ask).toHaveBeenCalledWith(
      expect.objectContaining({
        question: "Summarize the latest competitor movement",
        output: "report",
      }),
    );

    await fireEvent.click(screen.getByRole("button", { name: "Merge" }));

    await waitFor(() => {
      expect(mockedApi.fileToWiki).toHaveBeenCalledWith("output/report.md", "merge");
    });
    expect(onContentChanged).toHaveBeenCalledTimes(1);

    const openFiledArticle = await screen.findByRole("button", { name: "Open filed article" });
    await fireEvent.click(openFiledArticle);
    expect(onOpenArticle).toHaveBeenCalledWith("wiki/outputs/report.md");
  });
});
