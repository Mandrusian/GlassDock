"""Built-in themes. A theme is a set of overrides for schema keys.

Names with "-inspired" are visual homages only. Genuine background blur
needs SwayFX (Appearance > Background blur); without it, themes use plain
transparency.
"""

CUSTOM = "custom"
DEFAULT_THEME = "smoky-glass"

THEMES = {
    "smoky-glass": {
        "label": "Smoky Glass",
        "description": "Translucent charcoal with a soft border (default).",
        "values": {
            "appearance.bg_color": "#1d1d22",
            "appearance.bg_opacity": 0.72,
            "appearance.bg_gradient": False,
            "appearance.bg_color2": "#2c2c36",
            "appearance.gradient_direction": "vertical",
            "appearance.border_color": "#ffffff",
            "appearance.border_opacity": 0.16,
            "appearance.border_width": 1.0,
            "appearance.corner_radius": 22,
            "appearance.shadow": True,
            "appearance.shadow_size": 18,
            "appearance.shadow_opacity": 0.45,
            "appearance.label_bg": "#1d1d22",
            "appearance.label_color": "#ffffff",
            "indicators.color": "#ffffff",
            "indicators.active_color": "#8ab4ff",
        },
    },
    "dark": {
        "label": "Dark",
        "description": "Near-opaque dark panel.",
        "values": {
            "appearance.bg_color": "#111114",
            "appearance.bg_opacity": 0.90,
            "appearance.bg_gradient": False,
            "appearance.bg_color2": "#1c1c22",
            "appearance.gradient_direction": "vertical",
            "appearance.border_color": "#ffffff",
            "appearance.border_opacity": 0.08,
            "appearance.border_width": 1.0,
            "appearance.corner_radius": 18,
            "appearance.shadow": True,
            "appearance.shadow_size": 16,
            "appearance.shadow_opacity": 0.55,
            "appearance.label_bg": "#000000",
            "appearance.label_color": "#f0f0f0",
            "indicators.color": "#d8d8d8",
            "indicators.active_color": "#ffffff",
        },
    },
    "light": {
        "label": "Light",
        "description": "Bright frosted-white panel.",
        "values": {
            "appearance.bg_color": "#f4f4f7",
            "appearance.bg_opacity": 0.78,
            "appearance.bg_gradient": False,
            "appearance.bg_color2": "#e2e2ea",
            "appearance.gradient_direction": "vertical",
            "appearance.border_color": "#000000",
            "appearance.border_opacity": 0.10,
            "appearance.border_width": 1.0,
            "appearance.corner_radius": 22,
            "appearance.shadow": True,
            "appearance.shadow_size": 18,
            "appearance.shadow_opacity": 0.30,
            "appearance.label_bg": "#f4f4f7",
            "appearance.label_color": "#1a1a1a",
            "indicators.color": "#444444",
            "indicators.active_color": "#0a60ff",
        },
    },
    "macos-inspired": {
        "label": "macOS-inspired",
        "description": "Light translucent shelf with bright rim.",
        "values": {
            "appearance.bg_color": "#dcdce0",
            "appearance.bg_opacity": 0.42,
            "appearance.bg_gradient": False,
            "appearance.bg_color2": "#c8c8d0",
            "appearance.gradient_direction": "vertical",
            "appearance.border_color": "#ffffff",
            "appearance.border_opacity": 0.55,
            "appearance.border_width": 1.0,
            "appearance.corner_radius": 24,
            "appearance.shadow": True,
            "appearance.shadow_size": 20,
            "appearance.shadow_opacity": 0.35,
            "appearance.label_bg": "#3b3b3f",
            "appearance.label_color": "#ffffff",
            "indicators.color": "#2b2b2e",
            "indicators.active_color": "#2b2b2e",
        },
    },
    "liquid-glass-inspired": {
        "label": "Liquid Glass-inspired",
        "description": "Very clear panel with a bright rim. Best with SwayFX blur on.",
        "values": {
            "appearance.bg_color": "#ffffff",
            "appearance.bg_opacity": 0.10,
            "appearance.bg_gradient": True,
            "appearance.bg_color2": "#a8c8ff",
            "appearance.gradient_direction": "diagonal",
            "appearance.border_color": "#ffffff",
            "appearance.border_opacity": 0.45,
            "appearance.border_width": 1.5,
            "appearance.corner_radius": 30,
            "appearance.shadow": True,
            "appearance.shadow_size": 22,
            "appearance.shadow_opacity": 0.35,
            "appearance.label_bg": "#2a2f3a",
            "appearance.label_color": "#ffffff",
            "indicators.color": "#ffffff",
            "indicators.active_color": "#ffffff",
        },
    },
    "purple-pink": {
        "label": "Purple / Pink",
        "description": "Diagonal purple-to-pink gradient.",
        "values": {
            "appearance.bg_color": "#4a1f7a",
            "appearance.bg_opacity": 0.80,
            "appearance.bg_gradient": True,
            "appearance.bg_color2": "#d6336c",
            "appearance.gradient_direction": "diagonal",
            "appearance.border_color": "#ffffff",
            "appearance.border_opacity": 0.25,
            "appearance.border_width": 1.0,
            "appearance.corner_radius": 24,
            "appearance.shadow": True,
            "appearance.shadow_size": 20,
            "appearance.shadow_opacity": 0.45,
            "appearance.label_bg": "#3a1760",
            "appearance.label_color": "#ffffff",
            "indicators.color": "#ffe6f5",
            "indicators.active_color": "#ffffff",
        },
    },
}


def theme_names():
    return list(THEMES.keys()) + [CUSTOM]


def theme_label(name):
    if name == CUSTOM:
        return "Custom"
    return THEMES[name]["label"]
