# COPYRIGHT (C) 2025 Robin Hirst
# MIT

import json
import shlex
import re
from threading import Thread
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pynicotine.pluginsystem import BasePlugin, returncode
from pynicotine.events import events


DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"
PLUGIN_VERSION = "0.3.4"


class Plugin(BasePlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.settings = {
            "api_key": "",
            "target_lang": "DE",
            "preserve_formatting": True,
            "auto_translate_incoming": True,
            "auto_incoming_target_lang": "EN-GB",
        }

        self._last_public_message = {}
        self._last_private_message = {}
        self.metasettings = {
            "api_key": {
                "description": "DeepL API key:",
                "type": "string",
            },
            "target_lang": {
                "description": "Target language (e.g., EN-US, EN-GB, DE, ES, JA):",
                "type": "string",
            },
            "preserve_formatting": {
                "description": "Preserve simple formatting (bold/italic/newlines)",
                "type": "bool",
            },
            "auto_translate_incoming": {
                "description": "Auto-translate incoming messages (local only)",
                "type": "bool",
            },
            "auto_incoming_target_lang": {
                "description": "Target language for incoming messages (e.g., EN-US)",
                "type": "string",
            },
        }

        self.commands = {
            "translate": {
                "aliases": ["tr"],
                "description": "Translate text using DeepL and send the translation",
                "parameters": ["[target_lang]", "<text..>"],
                "parameters_chatroom": ["[target_lang]", "<text..>"],
                "parameters_private_chat": ["[target_lang]", "<text..>"],
                "callback": self.translate_command,
            },
            "trver": {
                "aliases": ["trversion"],
                "description": "Show DeepL Translate plugin version",
                "parameters": [],
                "callback": self.version_command,
            },
            "trincoming": {
                "aliases": ["tri"],
                "description": "Set target language for incoming auto-translation",
                "parameters": ["<target_lang>"],
                "callback": self.set_incoming_lang_command,
            },
            "trhelp": {
                "aliases": ["trh"],
                "description": "Show DeepL Translate help and current settings",
                "parameters": [],
                "callback": self.translate_help_command,
            },
        }

    def translate_command(self, args, user=None, room=None):
        lowered = args.strip().lower()
        if lowered in {"version", "-v", "--version"}:
            return self.version_command("", user=user, room=room)
        if lowered in {"help", "-h", "--help", "?"}:
            return self.translate_help_command("", user=user, room=room)

        try:
            tokens = shlex.split(args)
        except ValueError:
            tokens = args.split()

        if not tokens:
            self.output("Usage: /translate [TARGET_LANG] <text..>")
            return False

        target_lang = None
        first = tokens[0]
        first_clean = self._strip_wrapping_quotes(first)
        if self._looks_like_lang(first_clean):
            target_lang = first_clean
            text = " ".join(tokens[1:])
        else:
            text = " ".join(tokens)

        if not text.strip():
            if room is not None:
                last = self._last_public_message.get(room)
                if not last:
                    self.output("No recent message to translate")
                    return False
                _last_user, last_text = last
                translated = self._translate_via_deepl(last_text, target_lang=target_lang)
                if translated is None:
                    return False
                translated = self._strip_wrapping_quotes(translated.strip())
                self.echo_public(room, translated, message_type="command")
                return True

            if user is not None:
                last = self._last_private_message.get(user)
                if not last:
                    self.output("No recent message to translate")
                    return False
                _last_user, last_text = last
                translated = self._translate_via_deepl(last_text, target_lang=target_lang)
                if translated is None:
                    return False
                translated = self._strip_wrapping_quotes(translated.strip())
                self.echo_private(user, translated, message_type="command")
                return True

            self.output("Nothing to translate")
            return False

        translated = self._translate_via_deepl(text, target_lang=target_lang)
        if translated is None:
            return False
        translated = self._strip_wrapping_quotes(translated.strip())

        if room is not None:
            self.send_public(room, translated)
        elif user is not None:
            self.send_private(user, translated, show_ui=True, switch_page=False)
        else:
            self.output(translated)

        return True

    def version_command(self, _args, user=None, room=None):
        self.output(f"DeepL Translate v{PLUGIN_VERSION}")
        return True

    def translate_help_command(self, _args="", user=None, room=None):
        settings = self.settings
        auto_on = "on" if settings.get("auto_translate_incoming", True) else "off"
        lines = [
            f"DeepL Translate v{PLUGIN_VERSION}",
            "",
            f"Outgoing default target: {settings.get('target_lang')}",
            f"Incoming auto-translate: {auto_on} → {settings.get('auto_incoming_target_lang')}",
            "",
            "Usage:",
            "  /tr [TARGET_LANG] <text..>         send translation",
            "  /tr [TARGET_LANG]                  translate latest msg (local-only)",
            "  @LANG text                         inline shortcut; sends translation",
            "  @LANG                              translate latest msg (local-only)",
            "",
            "Utilities:",
            "  /tri <TARGET_LANG>                 set incoming auto target",
            "  /trver                              show version",
            "  /tr help                            this help",
            "",
            "Examples:",
            "  /tr FR how are you",
            "  /tr \"DE\" \"how are you\"",
            "  @ES buenos dias",
            "  @EN-GB",
        ]
        self.output("\n".join(lines))
        return True

    def set_incoming_lang_command(self, args, user=None, room=None):
        lang = args.strip().strip('"\'')
        if not self._looks_like_lang(lang):
            self.output("Invalid target language. Example: EN-GB, EN-US, DE, ES")
            return False
        self.settings["auto_incoming_target_lang"] = lang
        self.config.sections["plugins"][self.internal_name.lower()]["auto_incoming_target_lang"] = lang
        self.output(f"Incoming auto-translate target set to {lang}")
        return True

    def incoming_public_chat_notification(self, room, user, line):
        if user != self.core.users.login_username:
            self._last_public_message[room] = (user, line)
        if not self.settings.get("auto_translate_incoming", True):
            return
        if user == self.core.users.login_username:
            return

        target = self.settings.get("auto_incoming_target_lang") or "EN-GB"

        def on_success(result):
            translated, detected = result
            if not translated:
                return
            if (detected and detected.upper().startswith("EN")) or translated.strip() == line.strip():
                return
            label = f"[{(detected or '?').upper()}→{target}] {user}: "
            self.echo_public(room, label + translated, message_type="command")

        self._async_translate(line, target_lang=target, on_success=on_success, silent=True)

    def incoming_private_chat_notification(self, user, line):
        if user != self.core.users.login_username:
            self._last_private_message[user] = (user, line)
        if not self.settings.get("auto_translate_incoming", True):
            return
        if user == self.core.users.login_username:
            return

        target = self.settings.get("auto_incoming_target_lang") or "EN-GB"

        def on_success(result):
            translated, detected = result
            if not translated:
                return
            if (detected and detected.upper().startswith("EN")) or translated.strip() == line.strip():
                return
            label = f"[{(detected or '?').upper()}→{target}] {user}: "
            self.echo_private(user, label + translated, message_type="command")

        self._async_translate(line, target_lang=target, on_success=on_success, silent=True)

    def outgoing_public_chat_event(self, room, line):
        """
        Shortcuts:
        - @FR hello => translates 'hello' to FR and sends, original not sent
        - @FR       => translates last message in room to FR (local-only echo)
        """
        handled = self._handle_outgoing_shortcut(line, context=("chatroom", room))
        if handled:
            return returncode["zap"]
        return None

    def outgoing_private_chat_event(self, user, line):
        handled = self._handle_outgoing_shortcut(line, context=("private", user))
        if handled:
            return returncode["zap"]
        return None

    def _handle_outgoing_shortcut(self, line, context):
        match = re.match(r"^\s*@([A-Za-z][A-Za-z\-_]{1,9})\s*(.*)$", line)
        if not match:
            return False

        target = match.group(1)
        rest = match.group(2).strip()

        if not self._looks_like_lang(target):
            return False

        if rest:
            def on_success(result):
                translated, _detected = result
                if not translated:
                    return
                translated = self._strip_wrapping_quotes(translated.strip())
                if context[0] == "chatroom":
                    self.send_public(context[1], translated)
                else:
                    self.send_private(context[1], translated, show_ui=True, switch_page=False)
            self._async_translate(rest, target_lang=target, on_success=on_success, silent=False)
            return True

        if context[0] == "chatroom":
            last = self._last_public_message.get(context[1])
            if not last:
                self.output("No recent message to translate")
                return True
            last_user, last_text = last
            def on_success(result):
                translated, _detected = result
                if not translated:
                    return
                translated = self._strip_wrapping_quotes(translated.strip())
                label = f"[{target}] {last_user}: "
                self.echo_public(context[1], label + translated, message_type="command")
            self._async_translate(last_text, target_lang=target, on_success=on_success, silent=False)
            return True

        last = self._last_private_message.get(context[1])
        if not last:
            self.output("No recent message to translate")
            return True
        last_user, last_text = last
        def on_success(result):
            translated, _detected = result
            if not translated:
                return
            translated = self._strip_wrapping_quotes(translated.strip())
            label = f"[{target}] {last_user}: "
            self.echo_private(context[1], label + translated, message_type="command")
        self._async_translate(last_text, target_lang=target, on_success=on_success, silent=False)
        return True

    def _translate_via_deepl(self, text, target_lang=None):
        api_key = self.settings.get("api_key", "").strip()
        if not api_key:
            self.output("DeepL API key not set. Open Preferences → Plugins → DeepL Translate to configure.")
            return None

        params = {
            "auth_key": api_key,
            "text": text,
            "target_lang": (target_lang or self.settings.get("target_lang") or "EN-US"),
        }
        if self.settings.get("preserve_formatting", True):
            params["preserve_formatting"] = 1

        data = urlencode(params).encode("utf-8")
        request = Request(DEEPL_API_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})

        try:
            with urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", "replace")
        except Exception as error:
            self.output(f"DeepL request failed: {error}")
            return None

        try:
            payload = json.loads(body)
        except Exception:
            self.output("Failed to parse DeepL response")
            return None

        if "message" in payload and "error" in payload.get("message", "").lower():
            self.output(f"DeepL error: {payload.get('message')}")
            return None

        translations = payload.get("translations")
        if not translations:
            self.output("DeepL returned no translations")
            return None

        return translations[0].get("text", "")

    def _translate_and_detect(self, text, target_lang=None):
        """Translate and return (translated_text, detected_source_language).
        Returns (None, None) if an error occurred (and error already echoed)."""
        api_key = self.settings.get("api_key", "").strip()
        if not api_key:
            return (None, None)

        params = {
            "auth_key": api_key,
            "text": text,
            "target_lang": (target_lang or self.settings.get("target_lang") or "EN-US"),
        }
        if self.settings.get("preserve_formatting", True):
            params["preserve_formatting"] = 1

        data = urlencode(params).encode("utf-8")
        request = Request(DEEPL_API_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})

        try:
            with urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", "replace")
        except Exception:
            return (None, None)

        try:
            payload = json.loads(body)
        except Exception:
            return (None, None)

        translations = payload.get("translations")
        if not translations:
            return (None, None)

        first = translations[0]
        return (first.get("text", ""), first.get("detected_source_language"))

    def _async_translate(self, text, target_lang, on_success, silent=False):
        def worker():
            result = self._translate_and_detect(text, target_lang=target_lang)

            def deliver():
                translated, detected = result
                if translated is None and not silent:
                    return
                on_success((translated, detected))

            events.invoke_main_thread(deliver)

        Thread(target=worker, daemon=True).start()

    @staticmethod
    def _looks_like_lang(token):
        if not token or len(token) > 10:
            return False
        for ch in token:
            if not (ch.isalpha() or ch in {"-", "_"}):
                return False
        return True

    @staticmethod
    def _strip_wrapping_quotes(text: str) -> str:
        if len(text) >= 2:
            pairs = [("\"", "\""), ("'", "'")]
            for opener, closer in pairs:
                if text.startswith(opener) and text.endswith(closer):
                    return text[1:-1]
        return text
