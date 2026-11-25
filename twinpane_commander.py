#!/usr/bin/env python3
"""
TwinPane Commander - a Python-only, Total Commander-style file manager for macOS.
Uses only the Python standard library (tkinter, pathlib, shutil, os, etc.).
"""

import os
import sys
import shutil
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from datetime import datetime


APP_NAME = "TwinPane Commander"


def human_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


class FilePane(ttk.Frame):
    def __init__(self, master, app, side):
        super().__init__(master)
        self.app = app
        self.side = side
        self.current_path = Path.home()
        self.show_hidden = tk.BooleanVar(value=False)
        self.path_var = tk.StringVar(value=str(self.current_path))
        self.count_var = tk.StringVar(value="")
        self._build()
        self.refresh()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=4, pady=(4, 2))
        ttk.Button(top, text="←", width=3, command=self.go_back).pack(side="left")
        ttk.Button(top, text="↑", width=3, command=self.go_parent).pack(side="left", padx=(3, 0))
        ttk.Button(top, text="⌂", width=3, command=self.go_home).pack(side="left", padx=(3, 5))
        self.path_entry = ttk.Entry(top, textvariable=self.path_var)
        self.path_entry.pack(side="left", fill="x", expand=True)
        self.path_entry.bind("<Return>", lambda _e: self.go_to_entry())
        ttk.Button(top, text="Go", command=self.go_to_entry).pack(side="left", padx=(4, 0))

        opts = ttk.Frame(self)
        opts.pack(fill="x", padx=6, pady=(0, 3))
        ttk.Checkbutton(opts, text="Show hidden files", variable=self.show_hidden,
                        command=self.refresh).pack(side="left")
        ttk.Label(opts, textvariable=self.count_var).pack(side="right")

        columns = ("name", "size", "modified", "kind")
        self.tree = ttk.Treeview(self, columns=columns, show="headings",
                                 selectmode="extended", height=18)
        self.tree.heading("name", text="Name", command=lambda: self.sort_by("name"))
        self.tree.heading("size", text="Size", command=lambda: self.sort_by("size"))
        self.tree.heading("modified", text="Modified", command=lambda: self.sort_by("modified"))
        self.tree.heading("kind", text="Type", command=lambda: self.sort_by("kind"))
        self.tree.column("name", width=260, minwidth=130, anchor="w")
        self.tree.column("size", width=85, minwidth=65, anchor="e")
        self.tree.column("modified", width=135, minwidth=110, anchor="center")
        self.tree.column("kind", width=90, minwidth=70, anchor="w")

        ybar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=2)
        ybar.pack(side="right", fill="y", pady=2)
        xbar.pack(side="bottom", fill="x", padx=4)

        self.tree.bind("<Double-1>", self.open_selected)
        self.tree.bind("<Return>", self.open_selected)
        self.tree.bind("<BackSpace>", lambda _e: self.go_parent())
        self.tree.bind("<Button-3>", self.context_menu)
        self.tree.bind("<FocusIn>", lambda _e: self.app.set_active(self))

    def refresh(self):
        try:
            self.current_path = self.current_path.expanduser().resolve()
            if not self.current_path.is_dir():
                raise NotADirectoryError(str(self.current_path))
            entries = list(self.current_path.iterdir())
            if not self.show_hidden.get():
                entries = [p for p in entries if not p.name.startswith(".")]
            entries.sort(key=lambda p: (not self._is_dir(p), p.name.casefold()))
        except Exception as exc:
            messagebox.showerror("Cannot read folder", f"{self.current_path}\n\n{exc}")
            return

        self.tree.delete(*self.tree.get_children())
        for path in entries:
            try:
                is_dir = path.is_dir()
                stat = path.stat()
                size = "" if is_dir else human_size(stat.st_size)
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                kind = "Folder" if is_dir else (path.suffix[1:].upper() if path.suffix else "File")
                display = ("📁 " if is_dir else "   ") + path.name
                self.tree.insert("", "end", iid=str(path), values=(display, size, modified, kind))
            except (OSError, PermissionError):
                self.tree.insert("", "end", iid=str(path), values=(path.name, "", "", "Unavailable"))

        self.path_var.set(str(self.current_path))
        self.count_var.set(f"{len(entries)} items")
        self.app.update_status()

    @staticmethod
    def _is_dir(path):
        try:
            return path.is_dir()
        except OSError:
            return False

    def selected_paths(self):
        return [Path(item) for item in self.tree.selection()]

    def go_to(self, path):
        target = Path(path).expanduser()
        try:
            target = target.resolve(strict=True)
            if not target.is_dir():
                messagebox.showwarning("Not a folder", f"Not a folder:\n{target}")
                return
            self.current_path = target
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Navigation error", str(exc))

    def go_to_entry(self):
        self.go_to(self.path_var.get())

    def go_parent(self):
        parent = self.current_path.parent
        if parent != self.current_path:
            self.go_to(parent)

    def go_home(self):
        self.go_to(Path.home())

    def go_back(self):
        self.go_parent()

    def open_selected(self, _event=None):
        selected = self.selected_paths()
        if not selected:
            return
        path = selected[0]
        if path.is_dir():
            self.go_to(path)
        else:
            self.app.open_file(path)

    def sort_by(self, key):
        items = []
        for iid in self.tree.get_children():
            path = Path(iid)
            try:
                if key == "size":
                    sort_value = path.stat().st_size if path.is_file() else -1
                elif key == "modified":
                    sort_value = path.stat().st_mtime
                elif key == "kind":
                    sort_value = path.suffix.casefold()
                else:
                    sort_value = path.name.casefold()
                items.append((sort_value, iid))
            except OSError:
                items.append(("", iid))
        items.sort(key=lambda x: x[0])
        for index, (_value, iid) in enumerate(items):
            self.tree.move(iid, "", index)

    def context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Open", command=self.open_selected)
        menu.add_command(label="Copy to other pane (F5)", command=self.app.copy_to_other)
        menu.add_command(label="Move to other pane (F6)", command=self.app.move_to_other)
        menu.add_separator()
        menu.add_command(label="Rename (F2)", command=self.app.rename_selected)
        menu.add_command(label="New folder (F7)", command=self.app.new_folder)
        menu.add_command(label="Delete (F8)", command=self.app.delete_selected)
        menu.tk_popup(event.x_root, event.y_root)


class TwinPaneCommander:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1200x720")
        self.root.minsize(850, 520)
        self.active_pane = None
        self.jobs = queue.Queue()
        self.busy = False
        self._configure_style()
        self._build_ui()
        self.root.bind("<F5>", lambda _e: self.copy_to_other())
        self.root.bind("<F6>", lambda _e: self.move_to_other())
        self.root.bind("<F2>", lambda _e: self.rename_selected())
        self.root.bind("<F7>", lambda _e: self.new_folder())
        self.root.bind("<F8>", lambda _e: self.delete_selected())
        self.root.bind("<F9>", lambda _e: self.refresh_all())
        self.root.bind("<Escape>", lambda _e: self.cancel_job())
        self.root.after(100, self.poll_jobs)

    def _configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("aqua" if sys.platform == "darwin" else "clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=25)
        style.configure("Treeview.Heading", font=("", 10, "bold"))

    def _build_ui(self):
        toolbar = ttk.Frame(self.root, padding=(8, 7))
        toolbar.pack(fill="x")
        buttons = [
            ("Copy  F5", self.copy_to_other),
            ("Move  F6", self.move_to_other),
            ("Rename  F2", self.rename_selected),
            ("New folder  F7", self.new_folder),
            ("Delete  F8", self.delete_selected),
            ("Refresh  F9", self.refresh_all),
        ]
        for label, command in buttons:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Open in Finder", command=self.reveal_in_finder).pack(side="right", padx=3)

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=6, pady=(0, 5))
        self.left = FilePane(panes, self, "left")
        self.right = FilePane(panes, self, "right")
        panes.add(self.left, weight=1)
        panes.add(self.right, weight=1)
        self.left.tree.bind("<FocusIn>", lambda _e: self.set_active(self.left), add="+")
        self.right.tree.bind("<FocusIn>", lambda _e: self.set_active(self.right), add="+")
        self.set_active(self.left)

        bottom = ttk.Frame(self.root, padding=(8, 4))
        bottom.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="determinate", length=220)
        self.progress.pack(side="right", padx=(8, 2))
        self.job_status = ttk.Label(bottom, text="")
        self.job_status.pack(side="right")

        hint = ttk.Label(self.root,
            text="Shortcuts: F5 Copy  •  F6 Move  •  F2 Rename  •  F7 New folder  •  F8 Delete  •  F9 Refresh  •  Enter Open",
            anchor="center")
        hint.pack(fill="x", padx=5, pady=(0, 5))

    def set_active(self, pane):
        self.active_pane = pane
        self.update_status()

    def other_pane(self):
        return self.right if self.active_pane is self.left else self.left

    def update_status(self):
        if not hasattr(self, "status_var"):
            return
        pane = self.active_pane
        if pane:
            selected = pane.selected_paths()
            self.status_var.set(
                f"Active: {pane.current_path}    |    Selected: {len(selected)}"
            )

    def refresh_all(self):
        self.left.refresh()
        self.right.refresh()

    def open_file(self, path):
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def reveal_in_finder(self):
        pane = self.active_pane
        if not pane:
            return
        selected = pane.selected_paths()
        target = selected[0] if selected else pane.current_path
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(target)])
            else:
                self.open_file(target if target.is_dir() else target.parent)
        except Exception as exc:
            messagebox.showerror("Cannot open location", str(exc))

    def _selected_for_operation(self):
        if not self.active_pane:
            return []
        selected = self.active_pane.selected_paths()
        if not selected:
            messagebox.showinfo("Nothing selected", "Select one or more files or folders first.")
        return selected

    def _unique_destination(self, destination):
        if not destination.exists():
            return destination
        stem, suffix = destination.stem, destination.suffix
        counter = 1
        while True:
            candidate = destination.with_name(f"{stem} ({counter}){suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def copy_to_other(self):
        self._start_transfer(move=False)

    def move_to_other(self):
        self._start_transfer(move=True)

    def _start_transfer(self, move):
        if self.busy:
            messagebox.showinfo("Operation in progress", "Please wait for the current operation to finish.")
            return
        sources = self._selected_for_operation()
        if not sources:
            return
        destination_dir = self.other_pane().current_path
        # Prevent copying/moving a directory into itself or one of its descendants.
        for src in sources:
            try:
                if src.is_dir() and (destination_dir == src or src in destination_dir.parents):
                    messagebox.showerror("Invalid destination", f"Cannot transfer a folder into itself or its own subfolder:\n{src}")
                    return
            except OSError:
                pass
        action = "move" if move else "copy"
        if move and not messagebox.askyesno("Confirm move", f"Move {len(sources)} selected item(s) to:\n{destination_dir}?"):
            return
        self._run_job(action, sources, destination_dir)

    def _run_job(self, action, sources, destination_dir):
        self.busy = True
        self.progress.configure(maximum=max(len(sources), 1), value=0)
        self.job_status.configure(text=f"{action.title()}ing…")
        thread = threading.Thread(
            target=self._transfer_worker,
            args=(action, sources, destination_dir),
            daemon=True
        )
        thread.start()

    def _transfer_worker(self, action, sources, destination_dir):
        completed = 0
        errors = []
        for src in sources:
            try:
                if not src.exists():
                    raise FileNotFoundError(str(src))
                target = self._unique_destination(destination_dir / src.name)
                if action == "copy":
                    if src.is_dir():
                        shutil.copytree(src, target, copy_function=shutil.copy2)
                    else:
                        shutil.copy2(src, target)
                else:
                    shutil.move(str(src), str(target))
                completed += 1
                self.jobs.put(("progress", completed, len(sources), f"{action.title()}: {src.name}"))
            except Exception as exc:
                errors.append(f"{src.name}: {exc}")
                self.jobs.put(("progress", completed, len(sources), f"Error: {src.name}"))
        self.jobs.put(("done", action, completed, len(sources), errors))

    def poll_jobs(self):
        try:
            while True:
                item = self.jobs.get_nowait()
                if item[0] == "progress":
                    _, done, total, label = item
                    self.progress.configure(maximum=max(total, 1), value=done)
                    self.job_status.configure(text=f"{done}/{total} — {label}")
                elif item[0] == "done":
                    _, action, completed, total, errors = item
                    self.busy = False
                    self.refresh_all()
                    self.job_status.configure(text=f"{action.title()} complete")
                    summary = f"{action.title()} completed: {completed} of {total} item(s)."
                    if errors:
                        summary += "\n\nSome items could not be processed:\n" + "\n".join(errors[:12])
                        if len(errors) > 12:
                            summary += f"\n…and {len(errors) - 12} more."
                        messagebox.showwarning("Operation finished with errors", summary)
                    else:
                        messagebox.showinfo("Operation complete", summary)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_jobs)

    def cancel_job(self):
        # File operations are not interrupted mid-copy; this shortcut is reserved for future cancellable jobs.
        if self.busy:
            messagebox.showinfo("In progress", "The current file operation will finish safely. You can close this message and wait.")

    def rename_selected(self):
        if self.busy:
            return
        selected = self._selected_for_operation()
        if len(selected) != 1:
            if selected:
                messagebox.showinfo("Rename", "Select exactly one item to rename.")
            return
        src = selected[0]
        new_name = simpledialog.askstring("Rename", "New name:", initialvalue=src.name, parent=self.root)
        if not new_name:
            return
        if new_name in (".", "..") or Path(new_name).name != new_name:
            messagebox.showerror("Invalid name", "Enter a valid file or folder name.")
            return
        target = src.with_name(new_name)
        if target.exists():
            messagebox.showerror("Already exists", f"An item named '{new_name}' already exists.")
            return
        try:
            src.rename(target)
            self.active_pane.refresh()
        except Exception as exc:
            messagebox.showerror("Rename failed", str(exc))

    def new_folder(self):
        if self.busy or not self.active_pane:
            return
        name = simpledialog.askstring("New folder", "Folder name:", parent=self.root)
        if not name:
            return
        if name in (".", "..") or Path(name).name != name:
            messagebox.showerror("Invalid name", "Enter a valid folder name.")
            return
        target = self.active_pane.current_path / name
        try:
            target.mkdir()
            self.active_pane.refresh()
        except FileExistsError:
            messagebox.showerror("Already exists", "An item with that name already exists.")
        except Exception as exc:
            messagebox.showerror("Cannot create folder", str(exc))

    def delete_selected(self):
        if self.busy:
            return
        selected = self._selected_for_operation()
        if not selected:
            return
        names = "\n".join(p.name for p in selected[:8])
        if len(selected) > 8:
            names += f"\n…and {len(selected) - 8} more"
        if not messagebox.askyesno(
            "Confirm permanent deletion",
            f"Permanently delete {len(selected)} selected item(s)?\n\n{names}\n\nThis cannot be undone."
        ):
            return
        errors = []
        for path in selected:
            try:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        self.active_pane.refresh()
        if errors:
            messagebox.showwarning("Some items were not deleted", "\n".join(errors[:10]))


def main():
    root = tk.Tk()
    TwinPaneCommander(root)
    root.mainloop()


if __name__ == "__main__":
    main()
