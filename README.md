# spec-rag

SPEC-grag is a specification authoring assistant built around a fact-first
GraphRAG workflow.

## Vendor Checkout

`Cargo.toml` currently depends on `vendor/graphrag-rs/graphrag-core`.
The `vendor/graphrag-rs` directory is intentionally not committed because it is
an upstream checkout.

To prepare a fresh workspace:

```bash
mkdir -p vendor
git clone https://github.com/automataIA/graphrag-rs.git vendor/graphrag-rs
git -C vendor/graphrag-rs checkout c46e2872fe7adc40e736981f1bf01dc71d829401
```

The previous Claude-modified experiment is kept locally as
`vendor/graphrag-rs-claude-spike` and is also intentionally ignored.

