Compare the following two article passages about "{{concept}}".

## Schema and Workflow Guidance
{{schema_context}}

## Article A: {{article_a_title}}
{{article_a_content}}

## Article B: {{article_b_title}}
{{article_b_content}}

## Task
Classify their relationship as one of:
- CONTRADICTION: incompatible factual claims
- DISAGREEMENT: different methods/conclusions
- COMPATIBLE: no conflict (different emphasis, complementary information)

## Output Format
Respond with valid JSON:
```json
{
  "classification": "CONTRADICTION|DISAGREEMENT|COMPATIBLE",
  "claim_a": "exact text from Article A (if conflict)",
  "claim_b": "exact text from Article B (if conflict)",
  "source_a": "raw source reference",
  "source_b": "raw source reference",
  "severity": "critical|warning|info",
  "explanation": "1-2 sentence explanation"
}
```
