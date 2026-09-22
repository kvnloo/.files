-- Explicit bridge for config/hermes-liquid-glass/hypr/liquid-glass.conf.
-- Do not source the hyprlang fragment.
hl.window_rule({
  name = "hermes-liquid-glass-opaque",
  match = { class = "^(Hermes)$" },
  opacity = "1.0 1.0",
})
