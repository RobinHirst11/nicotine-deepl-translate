# DeepL Translate — Nicotine+ plugin

Adds fast translation to Nicotine+ chats using the DeepL API. Provides a `/translate` command, an `@LANG` shortcut, and optional auto-translation of incoming messages.

## Contributors

[![Contributors](https://contrib.rocks/image?repo=RobinHirst11/nicotine-deepl-translate&anon=0&columns=25&max=100&r=true)](https://github.com/thytom/dwmbar/graphs/contributors)

---

### Requirements
- Nicotine+ with plugin support
- A DeepL API key (free or Pro). Get one: [DeepL API](https://www.deepl.com/en/products/api)

---

### Install
1. Place this folder in your Nicotine+ plugins directory (or use Preferences >> Plugins >> Install) and restart Nicotine+.
2. Enable the plugin: Preferences >> Plugins >> DeepL Translate.
3. Set your DeepL API key and default target language.

---

### Usage
- Translate and send:
  - `/tr [TARGET_LANG] <text..>` (alias: `/translate`)
  - Examples: `/tr FR how are you`, `/tr "DE" "how are you"`
- Quick shortcut while typing:
  - `@LANG <text>` sends the translation, e.g. `@ES buenos dias`
  - `@LANG` alone translates the latest message (local echo)
- Incoming auto-translate (optional):
  - Toggle in Preferences → Plugins → DeepL Translate
  - Set target via command: `/tri <TARGET_LANG>` (e.g., `/tri EN-GB`)

Other commands: `/trhelp` (help), `/trver` (version)

---

### Notes
- Supports preserving simple formatting (newlines, bold/italic) when enabled.
- Target language examples: `EN-US`, `EN-GB`, `DE`, `ES`, `JA`.
