---
title: "Attention Is All You Need"
id: "vaswani-2017-attention"
source_url: "https://arxiv.org/abs/1706.03762"
author: "Vaswani et al."
clipped_at: "2024-03-15T10:00:00Z"
format: "markdown"
source: "web-clip"
word_count: 1200
content_hash: "sha256:abc123"
status: "raw"
---

# Attention Is All You Need

## Abstract
The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.

## Key Findings
- The Transformer architecture achieves state-of-the-art results on machine translation tasks
- Self-attention allows the model to attend to all positions in the input sequence simultaneously
- Multi-head attention enables the model to jointly attend to information from different representation subspaces
- The model is significantly more parallelizable than recurrent architectures
- Training time is reduced compared to RNN-based models

## Architecture
The Transformer follows an encoder-decoder structure using stacked self-attention and point-wise, fully connected layers. The encoder maps an input sequence to a sequence of continuous representations. The decoder generates an output sequence one element at a time.

### Self-Attention
Scaled dot-product attention computes attention weights as:
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k))V

### Multi-Head Attention
Multi-head attention allows the model to jointly attend to information from different representation subspaces at different positions. It consists of h parallel attention layers (heads).

## Results
- BLEU score of 28.4 on WMT 2014 English-to-German translation
- BLEU score of 41.0 on WMT 2014 English-to-French translation
- Training time: 3.5 days on 8 P100 GPUs

## Limitations
- The model's performance on tasks requiring very long-range dependencies has not been extensively tested
- The quadratic complexity of self-attention with respect to sequence length limits scalability
