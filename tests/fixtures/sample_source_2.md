---
title: "BERT: Pre-training of Deep Bidirectional Transformers"
id: "devlin-2019-bert"
source_url: "https://arxiv.org/abs/1810.04805"
author: "Devlin et al."
clipped_at: "2024-03-16T14:00:00Z"
format: "markdown"
source: "web-clip"
word_count: 1500
content_hash: "sha256:def456"
status: "raw"
---

# BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding

## Abstract
We introduce BERT, a new language representation model that stands for Bidirectional Encoder Representations from Transformers. Unlike previous models, BERT is designed to pre-train deep bidirectional representations from unlabeled text by jointly conditioning on both left and right context in all layers.

## Key Findings
- Bidirectional pre-training is crucial for language understanding tasks
- BERT uses masked language modeling (MLM) to enable bidirectional training
- The next sentence prediction (NSP) task helps capture relationships between sentences
- Fine-tuning BERT with just one additional output layer achieves state-of-the-art on 11 NLP tasks
- BERT demonstrates that scaling model size leads to consistent improvements

## Pre-training Tasks
### Masked Language Modeling
BERT randomly masks 15% of input tokens and trains the model to predict the masked tokens. This enables truly bidirectional representation learning, unlike GPT which can only attend to left context.

### Next Sentence Prediction
BERT is also trained to predict whether sentence B follows sentence A in the original text. This helps the model capture inter-sentence relationships.

## Architecture
BERT uses the transformer encoder architecture from Vaswani et al. (2017). BERT-base uses 12 transformer layers, 768 hidden dimensions, and 12 attention heads (110M parameters). BERT-large uses 24 layers, 1024 hidden dimensions, and 16 attention heads (340M parameters).

## Results
- BERT achieves state-of-the-art results on GLUE, SQuAD, and SWAG benchmarks
- BERT-large outperforms all previous models on all tasks
- The bidirectional approach provides significant improvements over left-to-right models like GPT

## Comparison with GPT
While GPT uses a left-to-right transformer decoder, BERT uses a bidirectional transformer encoder. BERT argues that bidirectional context is more important than unidirectional for understanding tasks, while GPT prioritizes generative capabilities.

## Limitations
- Pre-training is computationally expensive (4 days on 16 TPUs for BERT-large)
- The model is not designed for text generation tasks
- Masked token prediction creates a discrepancy between pre-training and fine-tuning
