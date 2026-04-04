---
title: "GPT-3: Language Models are Few-Shot Learners"
id: "brown-2020-gpt3"
source_url: "https://arxiv.org/abs/2005.14165"
author: "Brown et al."
clipped_at: "2024-03-17T09:30:00Z"
format: "markdown"
source: "web-clip"
word_count: 1800
content_hash: "sha256:ghi789"
status: "raw"
---

# Language Models are Few-Shot Learners

## Abstract
Recent work has demonstrated substantial gains on many NLP tasks through pre-training on a large corpus of text followed by fine-tuning on a specific task. We show that scaling up language models greatly improves task-agnostic, few-shot performance. GPT-3, an autoregressive language model with 175 billion parameters, achieves strong performance on many NLP tasks without fine-tuning.

## Key Findings
- GPT-3 demonstrates that scaling language models to 175B parameters enables emergent few-shot learning
- The model can perform tasks with just a natural language prompt and a few examples
- Few-shot performance improves smoothly with model scale
- GPT-3 can generate coherent articles, code, and creative writing
- In-context learning emerges as a property of scale

## Architecture
GPT-3 uses the same transformer decoder architecture as GPT-2, scaled to 175 billion parameters. It uses 96 transformer layers, 96 attention heads, and a context window of 2048 tokens.

## Scaling Laws
The paper demonstrates clear scaling laws:
- Performance improves log-linearly with model size
- Larger models are more sample-efficient
- Few-shot performance improves more rapidly with scale than fine-tuned performance

## Results
- GPT-3 achieves near state-of-the-art on many benchmarks without fine-tuning
- On some tasks, few-shot GPT-3 matches or exceeds fine-tuned BERT performance
- Strong performance on novel tasks like arithmetic, word unscrambling, and code generation

## Comparison with BERT
GPT-3 uses a unidirectional (left-to-right) architecture while BERT uses bidirectional. However, GPT-3's massive scale compensates for the architectural difference. GPT-3 contains approximately 175 billion parameters compared to BERT-large's 340 million.

## Limitations
- The model sometimes generates plausible-sounding but incorrect information
- Few-shot performance still lags behind fine-tuned models on some tasks
- Training required enormous compute resources (estimated $4.6M)
- The model can exhibit biases present in training data
