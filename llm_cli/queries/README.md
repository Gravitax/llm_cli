# Tree-sitter tags queries

These `*-tags.scm` files drive symbol extraction in `services/repomap.py`. Each
captures `@name.definition.*` and `@name.reference.*` nodes for one language,
feeding the PageRank ranking of the project context index.

## Attribution

Vendored from the [Aider](https://github.com/Aider-AI/aider) project
(`aider/queries/`), licensed under Apache License 2.0. The `typescript-tags.scm`
file comes from Aider's `tree-sitter-languages` set; the rest from its
`tree-sitter-language-pack` set. Language names match `grep_ast.parsers`.

To add a language, drop `<language>-tags.scm` here (the stem must equal the
`grep_ast` language name) and it is picked up automatically.
