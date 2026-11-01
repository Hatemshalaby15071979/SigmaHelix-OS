#!/usr/bin/env python3
"""
Theme — ADHD-friendly dark high-contrast theme for Company OS.
Clear sections, large buttons, minimal clutter, visual separation.
"""
import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Custom color palette — ADHD-friendly
COLORS = {
    "bg_main": "#1a1a2e",
    "bg_panel": "#16213e",
    "accent": "#00d4aa",
    "text_main": "#e0e0ff",
    "text_dim": "#a8a8cc",
    "warning": "#ff6b6b",
    "success": "#00d4aa",
    "panel_border": "#2a2a4e",
}

FONT_MAIN = ("Segoe UI", 14)
FONT_HEAD = ("Segoe UI", 20, "bold")
FONT_BTN = ("Segoe UI", 14, "bold")

class ThemeConfig:
    """Theme configuration used across the app."""
    colors = COLORS
    font_main = FONT_MAIN
    font_head = FONT_HEAD
    font_btn = FONT_BTN
