#!/usr/bin/env python3
"""AlmazikLauncher: красивый лаунчер Minecraft. Любая версия, моды, свой хостинг, прокси.

pip install customtkinter requests
python launcher.py
"""
import os
import shutil
import json
import math
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import requests

import netlayer
import skins
from core import Core, LOADERS, DEFAULTS

THEMES = {
    "dark": dict(BG="#0f1624", SIDE="#0a101b", PANEL="#162033", FIELD="#1d2a42", BORDER="#2a3b5c",
                 MUTED="#8aa0c0", TEXT="#eaf4ff", ON="#041a2b"),
    "light": dict(BG="#eef4fc", SIDE="#e1eaf7", PANEL="#ffffff", FIELD="#e6eefa", BORDER="#c6d6ec",
                  MUTED="#5b6f8f", TEXT="#10213a", ON="#ffffff"),
}

ACCENTS = {
    "Алмаз": ("#3cc8ff", "#22a6dd", "#1799e0", "#0e7fbf"),
    "Изумруд": ("#3ddc84", "#2fb86b", "#16a35a", "#0f8548"),
    "Аметист": ("#b48cff", "#9a6df0", "#7c4ddb", "#6537c0"),
    "Рубин": ("#ff6b81", "#e84d66", "#d93a56", "#b92c46"),
    "Золото": ("#ffc13d", "#e5a41f", "#e09200", "#bf7a00"),
}


def apply_theme(theme, accent):
    global BG, SIDE, PANEL, FIELD, BORDER, MUTED, TEXT, ON, ACCENT, ACCENT_H
    t = THEMES.get(theme, THEMES["dark"])
    BG, SIDE, PANEL, FIELD, BORDER, MUTED, TEXT, ON = (
        t[k] for k in ("BG", "SIDE", "PANEL", "FIELD", "BORDER", "MUTED", "TEXT", "ON"))
    a = ACCENTS.get(accent, ACCENTS["Алмаз"])
    i = 0 if theme != "light" else 2
    ACCENT, ACCENT_H = a[i], a[i + 1]
    ctk.set_appearance_mode("light" if theme == "light" else "dark")


apply_theme("dark", "Алмаз")
RES = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


ease_out = lambda t: 1 - (1 - t) ** 3
ease_in_out = lambda t: 3 * t * t - 2 * t ** 3


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("AlmazikLauncher")
        self.geometry("1000x690")
        self.minsize(960, 650)
        try:
            self.iconbitmap(str(RES / "icon.ico"))
        except Exception:
            pass

        self._p_cur = self._p_target = self._p_shown = 0.0
        self._dots, self.current, self._loaded = -1, None, False
        self._nav_token = self._mods_gen = 0
        self._sig, self._img_cache = {}, {}

        self.core = Core(status=self.set_status, progress=self.set_progress)
        c = self.core.cfg
        apply_theme(c["theme"], c["accent"])
        self.configure(fg_color=BG)
        self._init_vars()

        # Сначала строим интерфейс в фоне, но поверх него сразу вешаем заставку с полоской загрузки
        self._build_ui()
        self.show("play")

        if c.get("splash", True):
            self._show_splash_screen()

        threading.Thread(target=self.fetch_versions, daemon=True).start()
        self._tick()

    def _show_splash_screen(self):
        splash = ctk.CTkFrame(self, fg_color=BG)
        splash.place(relx=0, rely=0, relwidth=1, relheight=1)
        splash.lift()

        username = self.core.cfg.get("username", "Player")
        ctk.CTkLabel(splash, text="◆", font=("Segoe UI", 64), text_color=ACCENT).pack(expand=True, pady=(0, 10))
        ctk.CTkLabel(splash, text="AlmazikLauncher", font=ctk.CTkFont(size=32, weight="bold"), text_color=TEXT).pack()
        ctk.CTkLabel(splash, text=f"Добро пожаловать, {username}!", font=ctk.CTkFont(size=18), text_color=MUTED).pack(pady=(10, 0))

        # Добавляем красивую полоску загрузки на экран приветствия
        splash_bar = ctk.CTkProgressBar(splash, width=350, height=12, corner_radius=6, progress_color=ACCENT, fg_color=FIELD)
        splash_bar.pack(pady=25)
        splash_bar.set(0)

        def hide_splash():
            try:
                self.animate(300, lambda t: splash.place_configure(relx=t), splash.destroy, ease_in_out)
            except Exception:
                splash.destroy()

        # Растягиваем анимацию заставки ровно на 2.5 секунды (2500 мс)
        self.animate(2500, lambda t: splash_bar.set(t), hide_splash, ease_out)

    def _init_vars(self):
        c = self.core.cfg
        self._swiping = False
        self.versions, self.busy, self._pmax = [], False, 1
        self.var_user = ctk.StringVar(value=c["username"])
        self.var_ver = ctk.StringVar(value=c["version"])
        self.var_loader = ctk.StringVar(value=c["loader"])
        self.var_server = ctk.StringVar(value=c["server"])
        self.var_host = ctk.StringVar(value=c["hosting"])
        self.var_mirror = ctk.StringVar(value=c["mirror"])
        self.var_proxy = ctk.StringVar(value=c["proxy"])
        self.var_java = ctk.StringVar(value=c["java"])
        self.var_snap = ctk.BooleanVar(value=False)
        self.var_theme = ctk.StringVar(value="Светлая" if c["theme"] == "light" else "Тёмная")
        self.var_anim = ctk.BooleanVar(value=c["animations"])
        self.var_splash = ctk.BooleanVar(value=c["splash"])
        self.var_after = ctk.StringVar(value=c["after_launch"])
        self.var_jvm = ctk.StringVar(value=c["jvm_args"])
        self.var_mod_search = ctk.StringVar(value="")
        self.selected_catalog_id = None
        self.mod_installing = False

    def _log(self, text):
        try:
            log = Path.home() / ".mclauncher" / "crash.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + text + "\n")
        except OSError:
            pass

    def report_callback_exception(self, exc, val, tb):
        import traceback
        text = "".join(traceback.format_exception(exc, val, tb))
        self._log(text)
        if sys.stderr:
            print(text, file=sys.stderr)
        if time.time() - getattr(self, "_last_err", 0) > 5:
            self._last_err = time.time()
            messagebox.showerror("Ошибка в лаунчере", f"{val}\n\nПодробности: {Path.home() / '.mclauncher' / 'crash.log'}")

    def _build_ui(self):
        if "var_user" not in self.__dict__:
            self._init_vars()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=28, pady=24)
        self.content.grid_columnconfigure(0, weight=1)
        self.curtain = tk.Frame(self.content, bg=BG, bd=0, highlightthickness=0)
        
        self._builders = {"play": self._page_play, "skins": self._page_skins, "pack": self._page_pack,
                          "settings": self._page_settings}
        self.pages = {"play": self._page_play()}
        self._sig.clear()

    def _get_page(self, key):
        if key not in self.pages:
            self.pages[key] = self._builders[key]()
        return self.pages[key]

    def _populate(self, key):
        if key == "pack":
            self.refresh_mods()
        elif key == "skins":
            self.refresh_skins()

    def card(self, parent):
        return ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=16)

    def heading(self, parent, text, sub):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=28, weight="bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(parent, text=sub, text_color=MUTED, font=ctk.CTkFont(size=13)).pack(anchor="w", pady=(0, 16))

    def entry(self, parent, var, ph=""):
        return ctk.CTkEntry(parent, textvariable=var, placeholder_text=ph, height=38, corner_radius=10,
                            fg_color=FIELD, border_color=BORDER, text_color=TEXT)

    def button(self, parent, text, cmd, accent=False, danger=False, **kw):
        if danger:
            b = ctk.CTkButton(parent, text=text, command=cmd, height=40, corner_radius=10, fg_color="#e84d66",
                              hover_color="#d93a56", text_color="#ffffff",
                              font=ctk.CTkFont(weight="bold"), **kw)
        elif accent:
            b = ctk.CTkButton(parent, text=text, command=cmd, height=40, corner_radius=10, fg_color=ACCENT,
                              hover_color=ACCENT_H, text_color=ON,
                              font=ctk.CTkFont(weight="bold"), **kw)
        else:
            b = ctk.CTkButton(parent, text=text, command=cmd, height=40, corner_radius=10, fg_color=FIELD,
                              hover_color=BORDER, text_color=TEXT, **kw)
        if not danger:
            self.smooth_hover(b, ACCENT if accent else FIELD, ACCENT_H if accent else BORDER)
        return b

    def smooth_hover(self, btn, normal, hover):
        btn.configure(hover=False)
        fx = {"c": normal, "n": 0}

        def go(target):
            try:
                if str(btn.cget("state")) == "disabled":
                    return
            except Exception:
                return
            fx["n"] += 1
            n, start = fx["n"], fx["c"]

            def step(t):
                if fx["n"] == n:
                    try:
                        fx["c"] = mix(start, target, t)
                        btn.configure(fg_color=fx["c"])
                    except Exception:
                        pass
            self.animate(120, step)
        btn.bind("<Enter>", lambda e: go(hover), add="+")
        btn.bind("<Leave>", lambda e: go(normal), add="+")

    def field(self, card, row, text, widget):
        ctk.CTkLabel(card, text=text, text_color=MUTED, anchor="w").grid(row=row, column=0, sticky="w",
                                                                         padx=(22, 12), pady=10)
        widget.grid(row=row, column=1, sticky="ew", padx=(0, 22), pady=10)

    def segment(self, parent, values, var, command=None):
        bar = ctk.CTkFrame(parent, fg_color=FIELD, corner_radius=12)
        btns, state = {}, {}

        def paint(animated=True):
            try:
                for v, b in btns.items():
                    on = var.get() == v
                    if state.get(v) == on:
                        continue
                    state[v] = on
                    f0, f1 = (FIELD, ACCENT) if on else (ACCENT, FIELD)
                    t0, t1 = (TEXT, ON) if on else (ON, TEXT)
                    if animated:
                        self.animate(140, lambda k, b=b, f0=f0, f1=f1, t0=t0, t1=t1: b.configure(
                            fg_color=mix(f0, f1, k), text_color=mix(t0, t1, k)))
                    else:
                        b.configure(fg_color=f1, text_color=t1)
            except (tk.TclError, AttributeError):
                pass

        def pick(v):
            var.set(v)
            if command:
                command(v)
        for v in values:
            b = ctk.CTkButton(bar, text=v, height=34, corner_radius=9, fg_color=FIELD, hover=False,
                              text_color=TEXT, command=lambda v=v: pick(v))
            b.pack(side="left", expand=True, fill="x", padx=3, pady=3)
            btns[v] = b
        var.trace_add("write", lambda *a: paint())
        paint(False)
        return bar

    def switch(self, parent, var):
        return ctk.CTkSwitch(parent, text="", variable=var, progress_color=ACCENT)

    def swatches(self, parent):
        fr = ctk.CTkFrame(parent, fg_color="transparent")
        self.accent_btns = {}
        i = 0 if self.core.cfg["theme"] != "light" else 2
        for name, a in ACCENTS.items():
            sel = name == self.core.cfg["accent"]
            b = ctk.CTkButton(fr, text="✓" if sel else "", width=36, height=36, corner_radius=18, fg_color=a[i],
                              hover_color=a[i + 1], text_color=ON, border_width=3 if sel else 0, border_color=TEXT,
                              command=lambda n=name: self.select_accent(n))
            b.pack(side="left", padx=4)
            self.accent_btns[name] = b
        self.lbl_accent_name = ctk.CTkLabel(fr, text=self.core.cfg["accent"], text_color=MUTED)
        self.lbl_accent_name.pack(side="left", padx=10)
        return fr

    def select_accent(self, name):
        self.core.cfg["accent"] = name
        i = 0 if self.var_theme.get() != "Светлая" else 2
        for n, b in self.accent_btns.items():
            try:
                if b.winfo_exists():
                    a = ACCENTS[n]
                    sel = n == name
                    b.configure(text="✓" if sel else "", border_width=3 if sel else 0, fg_color=a[i], hover_color=a[i+1])
            except Exception:
                pass
        if hasattr(self, "lbl_accent_name"):
            try:
                if self.lbl_accent_name.winfo_exists():
                    self.lbl_accent_name.configure(text=name)
            except Exception:
                pass

    def _page_settings(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        self.heading(page, "Настройки", "Оформление, поведение лаунчера и параметры игры")
        sc = ctk.CTkScrollableFrame(page, fg_color="transparent")
        sc.pack(fill="both", expand=True)

        def block(title):
            card = self.card(sc)
            card.pack(fill="x", pady=(0, 14))
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=title, text_color=ACCENT, font=ctk.CTkFont(size=15, weight="bold")).grid(
                row=0, column=0, columnspan=2, sticky="w", padx=22, pady=(16, 2))
            return card

        look = block("Оформление")
        self.field(look, 1, "Тема", self.segment(look, ["Тёмная", "Светлая"], self.var_theme))
        self.field(look, 2, "Цвет акцента", self.swatches(look))
        self.field(look, 3, "Анимации", self.switch(look, self.var_anim))
        self.field(look, 4, "Заставка при запуске", self.switch(look, self.var_splash))

        beh = block("Поведение")
        self.field(beh, 1, "После запуска игры", self.segment(beh, ["Ничего", "Свернуть", "Закрыть"], self.var_after))
        jvm = self.entry(beh, self.var_jvm, "доп. параметры JVM, например -XX:+UseG1GC")
        self.field(beh, 2, "Параметры JVM", jvm)

        data = block("Данные и применение")
        row = ctk.CTkFrame(data, fg_color="transparent")
        self.button(row, "✓ Применить настройки", self.apply_settings_with_loading, accent=True, width=200).pack(side="left")
        self.button(row, "Открыть папку данных", self.open_data_dir, width=190).pack(side="left", padx=10)
        self.button(row, "Сбросить", self.reset_settings, width=110, danger=True).pack(side="left")
        self.field(data, 1, "Управление", row)

        about = block("О программе")
        ctk.CTkLabel(about, text="AlmazikLauncher 3.5\nсоздатель TakSebeAlmazik", text_color=TEXT,
                     justify="left", anchor="w").grid(row=1, column=0, columnspan=2, sticky="w", padx=22, pady=(4, 16))
        return page

    def apply_settings_with_loading(self):
        try:
            self.focus_set()
        except Exception:
            pass

        loading_overlay = ctk.CTkFrame(self, fg_color=BG)
        loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        loading_overlay.lift()

        ctk.CTkLabel(loading_overlay, text="◆", font=("Segoe UI", 56), text_color=ACCENT).pack(expand=True, pady=(0, 10))
        ctk.CTkLabel(loading_overlay, text="Применение настроек...", font=ctk.CTkFont(size=24, weight="bold"), text_color=TEXT).pack()
        
        load_bar = ctk.CTkProgressBar(loading_overlay, width=350, height=12, corner_radius=6, progress_color=ACCENT, fg_color=FIELD)
        load_bar.pack(pady=20)
        load_bar.set(0)

        theme_val = "light" if self.var_theme.get() == "Светлая" else "dark"
        accent_val = self.core.cfg["accent"]
        
        try:
            self.core.save(
                theme=theme_val,
                accent=accent_val,
                animations=bool(self.var_anim.get()),
                splash=bool(self.var_splash.get()),
                after_launch=self.var_after.get(),
                jvm_args=self.var_jvm.get().strip()
            )
        except Exception:
            pass

        self.animate(2500, lambda t: load_bar.set(t), lambda: self.finish_loading_overlay(loading_overlay), ease_out)

    def finish_loading_overlay(self, overlay):
        try:
            overlay.destroy()
        except Exception:
            pass
        try:
            self.focus_set()
            self._rebuild()
            self.set_status("Настройки успешно применены!")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def open_data_dir(self):
        path = Path.home() / ".mclauncher"
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def reset_settings(self):
        if not messagebox.askyesno("Сброс", "Сбросить настройки к значениям по умолчанию?"):
            return
        self.core.save(**{k: DEFAULTS[k] for k in ("theme", "accent", "animations", "splash", "after_launch", "jvm_args")})
        c = self.core.cfg
        self.var_theme.set("Светлая" if c["theme"] == "light" else "Тёмная")
        self.var_anim.set(c["animations"])
        self.var_splash.set(c["splash"])
        self.var_after.set(c["after_launch"])
        self.var_jvm.set(c["jvm_args"])
        try:
            self.focus_set()
            self._rebuild()
            self.set_status("Настройки сброшены!")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _rebuild(self):
        self.collect()
        cur = self.current or "play"
        cfg = self.core.cfg
        apply_theme(cfg["theme"], cfg["accent"])
        self.configure(fg_color=BG)
        self._nav_token += 1
        try:
            if hasattr(self, "side") and self.side.winfo_exists():
                self.side.destroy()
        except Exception:
            pass
        try:
            if hasattr(self, "content") and self.content.winfo_exists():
                self.content.destroy()
        except Exception:
            pass
        self._build_ui()
        self.fill_versions()
        self._p_shown, self._dots, self.current = -1.0, -1, None
        if self.busy:
            try:
                self.btn_play.configure(state="disabled", text="Подожди")
            except Exception:
                pass
        self.show(cur)

    def after_game(self):
        self.sync_back()
        act = self.core.cfg.get("after_launch", "Ничего")
        if act == "Свернуть":
            self.iconify()
        elif act == "Закрыть":
            self.after(1500, self.destroy)

    def animate(self, ms, step, done=None, ease=ease_out):
        if not self.core.cfg.get("animations", True):
            try:
                step(1.0)
            except (tk.TclError, AttributeError):
                return
            if done:
                done()
            return
        t0 = time.perf_counter()

        def tick():
            s = time.perf_counter()
            t = min(1.0, (s - t0) * 1000 / ms)
            try:
                step(ease(t))
            except tk.TclError:
                return
            except AttributeError:
                return
            if t < 1:
                self.after(12, tick)
            elif done:
                done()
        tick()

    def _tick(self):
        try:
            if self._p_cur != self._p_target:
                self._p_cur += (self._p_target - self._p_cur) * 0.3
                if abs(self._p_target - self._p_cur) < 0.003:
                    self._p_cur = self._p_target
            if self._p_shown != self._p_cur:
                self._p_shown = self._p_cur
                self.bar.set(self._p_cur)
            if self.busy:
                dots = int(time.time() * 3) % 4
                if dots != self._dots:
                    self._dots = dots
                    if hasattr(self, "btn_play") and self.btn_play.winfo_exists():
                        self.btn_play.configure(text="Подожди" + "." * dots)
            if getattr(self, "mod_installing", False):
                dots = int(time.time() * 3) % 4
                if hasattr(self, "btn_install_mod") and self.btn_install_mod.winfo_exists():
                    self.btn_install_mod.configure(text="Скачивание" + "." * dots)
        except (tk.TclError, AttributeError):
            pass
        self.after(33, self._tick)

    def _build_sidebar(self):
        side = self.side = ctk.CTkFrame(self, fg_color=SIDE, corner_radius=0, width=220)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        ctk.CTkLabel(side, text="◆  AlmazikLauncher", font=ctk.CTkFont(size=19, weight="bold"),
                     text_color=ACCENT).pack(padx=22, pady=(28, 26), anchor="w")
        self.nav = {}
        for key, label in [("play", "▶   Играть"), ("skins", "🧑   Скины"), ("pack", "📦   Сборка и моды"),
                           ("settings", "⚙   Настройки")]:
            b = ctk.CTkButton(side, text=label, anchor="w", height=44, corner_radius=10, fg_color="transparent",
                              hover_color=PANEL, text_color=MUTED, font=ctk.CTkFont(size=15, weight="bold"),
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=14, pady=3)
            self.nav[key] = b
        ctk.CTkLabel(side, text="создатель TakSebeAlmazik", text_color=ACCENT,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="bottom", pady=(0, 16))
        ctk.CTkLabel(side, text="любая версия • моды • свой хостинг", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack(side="bottom", pady=(0, 4))

    def show(self, key):
        if key == self.current:
            return
        page = self._get_page(key)
        for k, b in self.nav.items():
            on, was = k == key, k == self.current
            if on != was:
                bg, fg = ((SIDE, PANEL), (MUTED, ACCENT)) if on else ((PANEL, SIDE), (ACCENT, MUTED))
                self.animate(160, lambda t, b=b, bg=bg, fg=fg: b.configure(
                    fg_color=mix(*bg, t), text_color=mix(*fg, t)))
        first = self.current is None
        self.current = key
        self._nav_token += 1
        token = self._nav_token
        for k, pg in self.pages.items():
            if k != key:
                pg.place_forget()
        page.place(x=0, y=0, relwidth=1, relheight=1)
        if first or not self.core.cfg.get("animations", True):
            self._populate(key)
            return
        self.curtain.place(relx=0, rely=1.0, anchor="sw", relwidth=1, relheight=1.0)
        self.curtain.lift()
        self.update_idletasks()

        def go():
            if token != self._nav_token:
                return
            self._populate(key)
            self.update_idletasks()
            self._reveal(token)
        self.after(10, go)

    def _reveal(self, token, ms=180):
        def step(t):
            if token == self._nav_token:
                self.curtain.place_configure(relheight=max(0.001, 1 - t))

        def done():
            if token == self._nav_token:
                self.curtain.place_forget()
        self.animate(ms, step, done, ease=ease_out)

    def _page_play(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        self.heading(page, "Играть", "Выбери версию и загрузчик, остальное лаунчер сделает сам")
        card = self.card(page)
        card.pack(fill="x")
        card.grid_columnconfigure(1, weight=1)

        nick = self.entry(card, self.var_user, "Player")
        self.field(card, 0, "Ник игрока", nick)

        vf = ctk.CTkFrame(card, fg_color="transparent")
        vf.grid_columnconfigure(0, weight=1)
        self.cb_ver = ctk.CTkComboBox(vf, variable=self.var_ver, values=[""], height=38, corner_radius=10,
                                      fg_color=FIELD, border_color=BORDER, button_color=BORDER,
                                      dropdown_fg_color=PANEL, command=lambda v: self.refresh_mods())
        self.cb_ver.grid(row=0, column=0, sticky="ew")
        ctk.CTkSwitch(vf, text="Снапшоты", variable=self.var_snap, progress_color=ACCENT,
                      command=self.fill_versions).grid(row=0, column=1, padx=(14, 0))
        self.field(card, 1, "Версия", vf)

        seg = self.segment(card, LOADERS, self.var_loader, lambda v: self.refresh_mods())
        self.field(card, 2, "Загрузчик", seg)

        rf = ctk.CTkFrame(card, fg_color="transparent")
        rf.grid_columnconfigure(0, weight=1)
        self.lbl_ram = ctk.CTkLabel(rf, text="", width=60, text_color=TEXT)
        self.slider = ctk.CTkSlider(rf, from_=1, to=16, number_of_steps=15, progress_color=ACCENT,
                                    button_color=ACCENT, button_hover_color=ACCENT_H,
                                    command=lambda v: self.lbl_ram.configure(text=f"{int(v)} ГБ"))
        self.slider.set(self.core.cfg["ram_gb"])
        self.lbl_ram.configure(text=f"{int(self.slider.get())} ГБ")
        self.slider.grid(row=0, column=0, sticky="ew")
        self.lbl_ram.grid(row=0, column=1, padx=(10, 0))
        self.field(card, 3, "Память", rf)

        self.field(card, 4, "Сервер", self.entry(card, self.var_server, "адрес:порт (необязательно)"))
        self.field(card, 5, "Java", self.entry(card, self.var_java, "авто: нужная версия подберётся и скачается сама"))

        self.bar = ctk.CTkProgressBar(page, height=10, corner_radius=5, progress_color=ACCENT, fg_color=FIELD)
        self.bar.set(0)
        self.bar.pack(fill="x", pady=(22, 6))
        self.lbl_status = ctk.CTkLabel(page, text="Готов", text_color=MUTED, anchor="w", justify="left",
                                       wraplength=640)
        self.lbl_status.pack(fill="x")
        self.btn_play = ctk.CTkButton(page, text="ИГРАТЬ", height=58, corner_radius=14, fg_color=ACCENT,
                                      hover_color=ACCENT_H, text_color=ON,
                                      font=ctk.CTkFont(size=20, weight="bold"), command=self.on_play)
        self.btn_play.pack(fill="x", pady=(14, 0))
        return page

    def _page_pack(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        
        loader_name = self.var_loader.get()
        sub_text = f"{loader_name} — управление модами и каталог Modrinth"
        if loader_name.lower() == "vanilla":
            sub_text = "⚠️ Внимание: выбран Vanilla! Для установки модов выберите Fabric или Forge на вкладке «Играть»."

        self.heading(page, "Моды", sub_text)
        
        columns_frame = ctk.CTkFrame(page, fg_color="transparent")
        columns_frame.pack(fill="both", expand=True, pady=(0, 10))
        columns_frame.grid_columnconfigure((0, 1), weight=1, uniform="col")
        columns_frame.grid_rowconfigure(0, weight=1)

        # ЛЕВАЯ КОЛОНКА: Установлено
        left_card = self.card(columns_frame)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_card.grid_columnconfigure(0, weight=1)
        left_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(left_card, text="УСТАНОВЛЕНО", font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        
        self.mods_box = ctk.CTkScrollableFrame(left_card, fg_color="transparent")
        self.mods_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        left_btns = ctk.CTkFrame(left_card, fg_color="transparent")
        left_btns.grid(row=2, column=0, sticky="ew", padx=14, pady=14)
        
        self.button(left_btns, "Добавить .jar", self.on_add_mods, accent=True).pack(side="left", expand=True, fill="x", padx=2)
        self.button(left_btns, "Удалить", self.on_del_selected_mods, danger=True).pack(side="left", expand=True, fill="x", padx=2)
        self.button(left_btns, "Папка", self.on_open_mods).pack(side="left", expand=True, fill="x", padx=2)

        # ПРАВАЯ КОЛОНКА: Каталог Modrinth
        right_card = self.card(columns_frame)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right_card.grid_columnconfigure(0, weight=1)
        right_card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(right_card, text="КАТАЛОГ MODRINTH", font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(right_card, text="Нажмите на мод в списке, чтобы выбрать его", font=ctk.CTkFont(size=11), text_color=MUTED).grid(row=0, column=0, sticky="w", padx=16, pady=(20, 2))

        search_row = ctk.CTkFrame(right_card, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        search_row.grid_columnconfigure(0, weight=1)

        self.mod_search_entry = ctk.CTkEntry(search_row, textvariable=self.var_mod_search, placeholder_text="Введите название мода...", height=38, corner_radius=10, fg_color=FIELD, border_color=BORDER, text_color=TEXT)
        self.mod_search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.button(search_row, "Найти", self.search_modrinth, accent=True, width=90).grid(row=0, column=1)

        self.catalog_box = ctk.CTkScrollableFrame(right_card, fg_color="transparent")
        self.catalog_box.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        ctk.CTkLabel(self.catalog_box, text="Введите запрос и нажмите «Найти»", text_color=MUTED).pack(pady=40)

        right_btns = ctk.CTkFrame(right_card, fg_color="transparent")
        right_btns.grid(row=3, column=0, sticky="ew", padx=14, pady=14)
        self.btn_install_mod = self.button(right_btns, "↓ Установить выбранное", self.install_selected_catalog_mod, accent=True)
        self.btn_install_mod.pack(fill="x")

        return page

    def search_modrinth(self):
        query = self.var_mod_search.get().strip()
        for w in self.catalog_box.winfo_children():
            w.destroy()
        if not query:
            ctk.CTkLabel(self.catalog_box, text="Введите запрос для поиска", text_color=MUTED).pack(pady=40)
            return
        
        ctk.CTkLabel(self.catalog_box, text="Поиск в каталоге Modrinth...", text_color=MUTED).pack(pady=20)
        
        def fetch():
            try:
                r = requests.get(f"https://api.modrinth.com/v2/search?query={query}&facets=[[\"project_type:mod\"]]", timeout=10)
                data = r.json().get("hits", [])
                self.after(0, lambda: self._show_catalog_results(data))
            except Exception as e:
                self.after(0, lambda: ctk.CTkLabel(self.catalog_box, text=f"Ошибка поиска: {e}", text_color="#e84d66").pack(pady=20))
        
        threading.Thread(target=fetch, daemon=True).start()

    def _show_catalog_results(self, items):
        for w in self.catalog_box.winfo_children():
            w.destroy()
        if not items:
            ctk.CTkLabel(self.catalog_box, text="Ничего не найдено", text_color=MUTED).pack(pady=40)
            return
        
        self.catalog_cards = []
        for item in items:
            title = item.get("title", "Мод")
            desc = item.get("description", "")
            downloads = item.get("downloads", 0)
            pid = item.get("project_id")
            
            card = ctk.CTkFrame(self.catalog_box, fg_color=FIELD, corner_radius=10, cursor="hand2")
            card.pack(fill="x", pady=4, padx=4)
            self.catalog_cards.append((pid, card))
            
            lbl = ctk.CTkLabel(card, text=f"📦 {title}\n{desc[:60]}... (Скачиваний: {downloads:,})", text_color=TEXT, justify="left", anchor="w", cursor="hand2")
            lbl.pack(side="left", padx=12, pady=8, fill="x", expand=True)
            
            def select_mod(p=pid, c=card):
                self.selected_catalog_id = p
                for other_pid, other_card in self.catalog_cards:
                    try:
                        other_card.configure(border_width=0)
                    except Exception:
                        pass
                try:
                    c.configure(border_width=2, border_color=ACCENT)
                except Exception:
                    pass
                self.set_status(f"Выбран мод: {title}")

            card.bind("<Button-1>", lambda e, p=pid, c=card: select_mod(p, c))
            lbl.bind("<Button-1>", lambda e, p=pid, c=card: select_mod(p, c))

    def install_selected_catalog_mod(self):
        project_id = getattr(self, "selected_catalog_id", None)
        if not project_id:
            messagebox.showwarning("Каталог", "Сначала нажмите на нужный мод в списке, чтобы выбрать его!")
            return
        ver = self.var_ver.get()
        if not ver:
            messagebox.showwarning("Версия", "Сначала выберите версию Minecraft на вкладке «Играть»")
            return
        
        loader = self.var_loader.get()
        if loader.lower() == "vanilla":
            messagebox.showerror("Ошибка загрузчика", "Моды нельзя установить на чистую Vanilla!\nПерейдите на вкладку «Играть» и выберите загрузчик Fabric или Forge.")
            return

        self.mod_installing = True
        if hasattr(self, "btn_install_mod"):
            try:
                self.btn_install_mod.configure(state="disabled")
            except Exception:
                pass

        self.set_status("Скачивание мода с Modrinth...")
        def do_install():
            try:
                r = requests.get(f"https://api.modrinth.com/v2/project/{project_id}/version?loaders=[\"{loader.lower()}\"]&game_versions=[\"{ver}\"]", timeout=15)
                versions = r.json()
                if not versions:
                    raise RuntimeError(f"У этого мода нет версий для загрузчика {loader} под версию игры {ver}.\nПопробуйте выбрать другой загрузчик (например, Fabric) на вкладке «Играть»..")
                files = versions[0].get("files", [])
                if not files:
                    raise RuntimeError("У файла мода нет скачиваемых файлов")
                file_url = files[0].get("url")
                filename = files[0].get("filename")
                
                dest = self.core.instance_dir(ver, loader) / "mods" / filename
                netlayer.download(file_url, dest)
                self.set_status(f"Мод {filename} успешно установлен!")
                self.after(0, lambda: self.refresh_mods(force=True))
            except Exception as e:
                messagebox.showerror("Ошибка установки", str(e))
                self.set_status("Ошибка установки мода")
            finally:
                self.mod_installing = False
                def reset_btn():
                    if hasattr(self, "btn_install_mod") and self.btn_install_mod.winfo_exists():
                        self.btn_install_mod.configure(state="normal", text="↓ Установить выбранное")
                self.after(0, reset_btn)

        threading.Thread(target=do_install, daemon=True).start()

    def refresh_mods(self, force=False):
        if "pack" not in self.pages:
            return
        if self.current != "pack":
            self._sig.pop("mods", None)
            return
        ver, loader = self.var_ver.get(), self.var_loader.get()
        mods = sorted((self.core.instance_dir(ver, loader) / "mods").glob("*.jar")) if ver else []
        sig = (ver, loader, tuple(m.name for m in mods))
        if not force and self._sig.get("mods") == sig:
            return
        self._sig["mods"] = sig
        self._mods_gen += 1
        for w in self.mods_box.winfo_children():
            w.destroy()
        if not mods:
            ctk.CTkLabel(self.mods_box, text="Модов пока нет", text_color=MUTED).pack(pady=40)
            return
        
        self.mod_vars = {}
        for m in mods:
            row = ctk.CTkFrame(self.mods_box, fg_color=FIELD, corner_radius=10)
            row.pack(fill="x", pady=3, padx=4)
            
            var = ctk.BooleanVar(value=False)
            self.mod_vars[m] = var
            
            cb = ctk.CTkCheckBox(row, text="🧩  " + m.name, variable=var, fg_color=ACCENT, text_color=TEXT)
            cb.pack(side="left", padx=12, pady=9)
            
            size_mb = f"{m.stat().st_size / (1024*1024):.1f} MB"
            ctk.CTkLabel(row, text=size_mb, text_color=MUTED).pack(side="right", padx=14)

    def on_del_selected_mods(self):
        to_del = [path for path, var in getattr(self, "mod_vars", {}).items() if var.get()]
        if not to_del:
            messagebox.showwarning("Удаление", "Выберите галочками моды для удаления")
            return
        if not messagebox.askyesno("Удаление", f"Удалить выбранные моды ({len(to_del)} шт.)?"):
            return
        for path in to_del:
            path.unlink(missing_ok=True)
        self.refresh_mods(force=True)

    def _page_skins(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        self.heading(page, "Скины", "Скин локальный: применяется в игре при запуске, другие игроки его не увидят")
        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 12))
        self.var_nick = ctk.StringVar()
        self.button(bar, "+ Загрузить PNG", self.on_skin_upload, accent=True, width=150).pack(side="left")
        self.entry(bar, self.var_nick, "ник, чей скин скачать").pack(side="left", fill="x", expand=True, padx=10)
        self.button(bar, "Скачать", self.on_skin_nick, width=100).pack(side="left")
        self.button(bar, "Сбросить", lambda: self.pick_skin(""), width=100).pack(side="left", padx=(8, 0))
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.skin_big = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=16, width=250)
        self.skin_big.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        self.skin_big.grid_propagate(False)
        self.skin_list = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self.skin_list.grid(row=0, column=1, sticky="nsew")
        self.skin_list.grid_columnconfigure((0, 1), weight=1)
        return page

    def preview(self, sid, scale):
        meta = skins.load_index().get(sid, {"slim": False, "name": sid})
        key = (sid, meta.get("slim", False), scale)
        if key not in self._img_cache:
            im = skins.render_preview(skins.get_image(sid), meta.get("slim", False), scale)
            if im:
                self._img_cache[key] = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
        return self._img_cache.get(key)

    def refresh_skins(self, force=False):
        if "skins" not in self.pages:
            return
        idx, active = skins.load_index(), self.core.cfg["skin"]
        if self.current != "skins":
            self._sig.pop("skins", None)
            return
        sig = json.dumps([idx, active], sort_keys=True)
        if not force and self._sig.get("skins") == sig:
            return
        self._sig["skins"] = sig
        for w in (*self.skin_big.winfo_children(), *self.skin_list.winfo_children()):
            w.destroy()
        bold = ctk.CTkFont(size=15, weight="bold")
        ctk.CTkLabel(self.skin_big, text="СЕЙЧАС В ИГРЕ", text_color=MUTED,
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(18, 6))
        if active in idx:
            img = self.preview(active, 6)
            if img:
                ctk.CTkLabel(self.skin_big, text="", image=img).pack(pady=10)
            ctk.CTkLabel(self.skin_big, text=idx[active]["name"], text_color=ACCENT,
                         font=ctk.CTkFont(size=18, weight="bold")).pack()
            ctk.CTkLabel(self.skin_big, text="тонкие руки (Alex)" if idx[active]["slim"] else "классика (Steve)",
                         text_color=MUTED).pack()
        else:
            ctk.CTkLabel(self.skin_big, text="Стандартный скин\nзагрузи PNG или скачай по нику",
                         text_color=MUTED, justify="center").pack(expand=True)
        for i, (sid, meta) in enumerate(idx.items()):
            card = ctk.CTkFrame(self.skin_list, fg_color=PANEL, corner_radius=14, border_width=2,
                                border_color=ACCENT if sid == active else PANEL)
            card.grid(row=i // 2, column=i % 2, padx=6, pady=6, sticky="nsew")
            img = self.preview(sid, 4)
            if img:
                ctk.CTkLabel(card, text="", image=img).pack(pady=(12, 4))
            ctk.CTkLabel(card, text=meta["name"], text_color=TEXT, font=bold).pack()
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(pady=(6, 12))
            ctk.CTkButton(row, text="Выбран" if sid == active else "Выбрать", width=84, height=30,
                          fg_color=FIELD if sid == active else ACCENT, hover_color=ACCENT_H,
                          text_color=TEXT if sid == active else ON,
                          command=lambda s=sid: self.pick_skin(s)).pack(side="left", padx=3)
            ctk.CTkButton(row, text="Alex" if meta["slim"] else "Steve", width=56, height=30, fg_color=FIELD,
                          hover_color=BORDER, text_color=TEXT,
                          command=lambda s=sid, m=meta: (skins.set_slim(s, not m["slim"]), self.refresh_skins())
                          ).pack(side="left", padx=3)
            ctk.CTkButton(row, text="✕", width=30, height=30, fg_color="transparent", hover_color="#a33",
                          command=lambda s=sid: self.delete_skin(s)).pack(side="left", padx=3)

    def pick_skin(self, sid):
        self.core.save(skin=sid)
        self.refresh_skins()
        self.set_status("Скин применится при следующем запуске игры" if sid else "Скин сброшен")

    def delete_skin(self, sid):
        skins.delete_skin(sid)
        if self.core.cfg["skin"] == sid:
            self.core.save(skin="")
        self.refresh_skins()

    def on_skin_upload(self):
        path = filedialog.askopenfilename(filetypes=[("PNG-скин", "*.png")])
        if not path:
            return
        try:
            self.pick_skin(skins.add_skin(Path(path).stem, path))
        except Exception as e:
            messagebox.showerror("Скин", str(e))

    def on_skin_nick(self):
        nick = self.var_nick.get().strip()
        self.run_bg(lambda: self.core.save(skin=skins.add_skin(nick, skins.fetch_by_nick(nick))),
                    self.refresh_skins)

    def set_status(self, text):
        try:
            if hasattr(self, "lbl_status") and self.lbl_status.winfo_exists():
                self.lbl_status.configure(text=text)
        except Exception:
            pass

    def set_progress(self, value, maximum=None):
        if maximum is not None:
            self._pmax = max(maximum, 1)
        self._p_target = min(1.0, value / self._pmax)
        if value == 0:
            self._p_cur = 0.0

    def fetch_versions(self):
        self.set_status("Загрузка списка версий...")
        try:
            self.versions = self.core.get_versions()
            self.set_status("Готов")
        except Exception as e:
            self.versions = []
            self.set_status(f"Не удалось получить версии: {e}")
        self._loaded = True
        self.after(0, self.fill_versions)

    def fill_versions(self):
        allowed = {"release", "snapshot", "old_beta", "old_alpha"} if self.var_snap.get() else {"release"}
        ids = [v["id"] for v in self.versions if v.get("type") in allowed] or [""]
        try:
            if hasattr(self, "cb_ver") and self.cb_ver.winfo_exists():
                self.cb_ver.configure(values=ids)
        except Exception:
            pass
        if not self.var_ver.get() and ids[0]:
            self.var_ver.set(ids[0])
            self.refresh_mods()

    def collect(self):
        self.core.save(username=self.var_user.get().strip() or "Player", ram_gb=int(self.slider.get()),
                       version=self.var_ver.get(), loader=self.var_loader.get(),
                       hosting=self.var_host.get().strip(), server=self.var_server.get().strip(),
                       mirror=self.core.cfg.get("mirror", "Авто"), proxy=self.core.cfg.get("proxy", ""),
                       java=self.var_java.get().strip(), animations=bool(self.var_anim.get()),
                       splash=bool(self.var_splash.get()), after_launch=self.var_after.get(),
                       jvm_args=self.var_jvm.get().strip())

    def on_play(self):
        self.collect()
        self.run_bg(self.core.play, self.after_game)

    def on_sync(self):
        self.collect()
        self.run_bg(self.core.sync, self.sync_back)

    def sync_back(self):
        c = self.core.cfg
        self.var_ver.set(c["version"])
        self.var_loader.set(c["loader"])
        self.var_server.set(c["server"])
        self.refresh_mods(force=True)

    def on_open_mods(self):
        path = self.core.instance_dir(self.var_ver.get(), self.var_loader.get()) / "mods"
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def on_add_mods(self):
        if not self.var_ver.get():
            return messagebox.showwarning("Версия", "Сначала выберите версию")
        dest = self.core.instance_dir(self.var_ver.get(), self.var_loader.get()) / "mods"
        dest.mkdir(parents=True, exist_ok=True)
        for f in filedialog.askopenfilenames(filetypes=[("Mods", "*.jar")]):
            shutil.copy(f, dest)
        self.refresh_mods(force=True)

    def run_bg(self, job, done=None):
        if self.busy:
            return
        self.busy = True
        try:
            if hasattr(self, "btn_play") and self.btn_play.winfo_exists():
                self.btn_play.configure(state="disabled", text="Подожди...")
        except Exception:
            pass

        def wrapper():
            try:
                job()
                if done:
                    self.after(0, done)
            except Exception as e:
                hint = ""
                if isinstance(e, requests.exceptions.SSLError):
                    hint = ("\n\nSSL-ошибка: проверь дату и время в системе, отключи HTTPS-сканирование "
                            "в антивирусе или включи VPN.")
                elif isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
                    hint = ("\n\nСервер не ответил. Проверь интернет или VPN. Уже установленные версии "
                            "запускаются без сети.")
                self.after(0, lambda: messagebox.showerror("Ошибка", f"{e}{hint}"))
                self.set_status("Ошибка")
            finally:
                self.busy = False
                def reset_btn():
                    try:
                        if hasattr(self, "btn_play") and self.btn_play.winfo_exists():
                            self.btn_play.configure(state="normal", text="ИГРАТЬ")
                    except Exception:
                        pass
                self.after(0, reset_btn)
        threading.Thread(target=wrapper, daemon=True).start()


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        import traceback
        text = traceback.format_exc()
        try:
            log = Path.home() / ".mclauncher" / "crash.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + text + "\n")
        except OSError:
            pass
        try:
            messagebox.showerror("AlmazikLauncher не запустился", text[-1500:])
        except Exception:
            pass
        raise