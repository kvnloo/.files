# Tern phone controls

Phone-only window plugin for the Omalauncher Arch ARM guest. Install this package on the phone, not in the desktop's shared `config/tern/plugins`.

```sh
tern plugin install /path/to/config/tern-phone/phone-controls
```

Run **Phone controls: enable** from Tern's command picker. It sets the local font size to 15, enables the status bar and selects Reader chat style. Settings stay in the existing configuration/state directories. The bar offers Hosts, Sessions, Prev, Next and More. More opens all commands, including Zoom, Copy, Paste, Phone: Escape, Phone: Tab and Phone: interrupt focused agent. Interrupt uses the focused agent only and does not close its block. Phone controls: hide removes the extra bar segments without resetting other settings.

No shared splits, tabs or desktop settings are rearranged. Plugin CSS uses `tern.css`, not manifest styles that would travel to remote clients. The plugin loads only where installed. Saved phone settings persist; profile enable is explicit so reload does not overwrite a font size chosen later.

Verified on the actual phone Tern 0.8.0 ARM64 binary at 480x979 scale 3: host button opens the Hosts picker, Prev changes active tabs, More opens Commands, profile sets font 15/status bar, and the controls render in the live phone window. Physical keyboard-open and touch-hit-area checks still need phone interaction. The status bar can compress controls when other status content is long.

The installed Android launcher remains Play-signed. Dictation and multi-touch compositor changes require a compatible signed launcher release. Do not uninstall the launcher or replace its private Linux data to bypass APK certificate mismatch.
