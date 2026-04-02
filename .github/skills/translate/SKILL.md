---
name: translate
description: Translate paper markdown to a target language (default Chinese). Preserves LaTeX formulas, code blocks, and images. Supports single paper or batch translation. Use when the user wants to read papers in their native language or translate non-Chinese documents.
version: 1.0.0
author: Vinnish-A/AutoR
license: MIT
tags: ["academic", "papers", "translation", "multilingual"]
---
# 论文翻译

将论文 Markdown 翻译为目标语言（默认中文），保留 LaTeX 公式、代码块、图片引用和 Markdown 格式。翻译结果保存为 `paper_{lang}.md`，原文保持不变。

## 配置

`config.yaml` 中可设置默认行为：

```yaml
translate:
  auto_translate: false   # 入库时是否自动翻译（默认关闭）
  target_lang: zh          # 目标语言（zh/en/ja/ko/de/fr/es）
  chunk_size: 4000         # 分块大小（字符数）
  concurrency: 5           # 并发翻译数
```

每次调用时可通过 CLI 参数覆盖默认值。

## 执行逻辑

### 单篇翻译

```bash
autor translate "<paper-id>" [--lang zh] [--force]
```

### 批量翻译

```bash
autor translate --all [--lang zh] [--force]
```

### 查看翻译

```bash
autor show "<paper-id>" --layer 4 --lang zh
```

### 作为 pipeline 步骤

```bash
autor pipeline --steps toc,l3,translate
```

> **注意**：`translate` 默认不在预设（`full`/`ingest`/`enrich`/`reindex`）中；可通过 `--steps` 显式指定。若 `config.translate.auto_translate=true` 且 pipeline 包含 inbox 步骤，`translate` 会在 papers 阶段自动注入。

## 工作流程

1. 检测论文原文语言（基于字符集启发式检测）
2. 如果已是目标语言，跳过
3. 将 Markdown 按段落边界分块（保留代码块和公式完整性）
4. 通过 LLM 逐块翻译，保留所有格式标记
5. 合并翻译结果，保存为 `paper_{lang}.md`
6. 在 `meta.json` 中记录翻译元数据

## 示例

用户说："把这篇英文论文翻译成中文"
-> 执行 `autor translate "<paper-id>" --lang zh`

用户说："把所有论文翻译成中文"
-> 执行 `autor translate --all --lang zh`

用户说："看这篇论文的中文版"
-> 执行 `autor show "<paper-id>" --layer 4 --lang zh`

用户说："重新翻译这篇论文"
-> 执行 `autor translate "<paper-id>" --force`
