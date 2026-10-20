# 0.7.2

- Add a per-live H.264/HEVC output codec option when the connected engine supports it.
- HEVC is available with a working VAAPI encoder.

# 0.7.1

- Fix adding announcements when Home Assistant is accessed over HTTP.
- Generate collision-safe announcement IDs without secure-context browser APIs.
- Disable the add button with an explanation at the 32-announcement limit.

# 0.7.0

- Bundled per-live vertical announcement editor with live speed and content updates.
- Select classic/full-height layout and weather footer without restarting the stream.

# 0.6.4

- Accept complete camera score JSON returned as text or in a Markdown JSON fence.
- Validate every score before submitting a camera comparison.

# 0.6.3

- Configure separate local-time camera bonuses for morning and evening.
- Expose both bonus strengths as independent Home Assistant numbers per live.
- Remove the global daytime bonus and its camera selector.

## 0.5.0

- Bundled per-live overlay editor with live layout controls and composed previews.
- Independent camera, date and time visibility; bar placement, text style and motion.
- Authenticated editor API with administrator-only writes and sanitized responses.
- Retain existing entities, multi-live controls and compatibility with older engines.
