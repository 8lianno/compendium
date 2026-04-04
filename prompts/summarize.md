You are a research analyst. Produce a structured summary of the following source document.

## Source
Title: {{title}}
Word count: {{word_count}}

## Content
{{content}}

## Output Format
Respond with valid JSON matching this structure:
```json
{
  "source": "{{source_id}}",
  "title": "{{title}}",
  "summary": "2-3 sentence overview",
  "claims": [
    {
      "claim": "specific factual assertion",
      "evidence": "supporting evidence from text",
      "section": "section heading where claim appears",
      "confidence": "high|medium|low"
    }
  ],
  "methodology": "how the source conducted its analysis (if applicable, else null)",
  "findings": ["key finding 1", "key finding 2"],
  "limitations": ["limitation 1", "limitation 2"],
  "concepts": ["concept1", "concept2", "concept3"]
}
```

Rules:
- Every claim must be directly supported by text in the source
- Do not infer or extrapolate beyond what is stated
- List ALL distinct concepts, entities, methods, and theories mentioned
- Include concept aliases (e.g., if the text says "ML" and "machine learning", list both)
- confidence: "high" if explicitly stated with evidence, "medium" if implied, "low" if tangential
