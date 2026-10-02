# Newzi bundled fonts

Inter and Newsreader are sourced from the official Google Fonts repository and distributed under SIL Open Font License 1.1. The variable TTF files are bundled offline so the native client does not depend on runtime downloads.

- `Inter.ttf`: UI, labels, metadata, buttons and navigation.
- `Newsreader.ttf`: editorial headlines.

The family boundary is centralized in `src/theme/index.ts` (`typography.fontFamily`).
