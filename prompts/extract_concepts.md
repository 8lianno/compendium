You are a taxonomy construction engine. Given these source summaries, build a hierarchical concept taxonomy.

## Source Summaries
{{summaries}}

## Output Format
Respond with valid JSON:
```json
{
  "taxonomy": [
    {
      "canonical_name": "Machine Learning",
      "aliases": ["ML", "machine learning"],
      "category": "concepts",
      "parent": null,
      "source_count": 12,
      "sources": ["source-a", "source-b"],
      "should_generate_article": true,
      "article_generation_reason": "Referenced in 12 sources with 8 distinct claims"
    }
  ]
}
```

Rules:
- Merge synonyms and abbreviations into single canonical entries
- Establish parent-child relationships where clear
- Assign each concept to exactly one category: concepts | methods | entities | theories
- For each concept, list: canonical_name, aliases[], category, source_count, parent (if any)
- Sort by source_count descending within each category
- A concept must appear in at least 1 source to be included
- Set should_generate_article=true if source_count >= 2 or distinct claims >= 5
