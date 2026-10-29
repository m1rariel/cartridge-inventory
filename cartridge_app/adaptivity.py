"""Small Tk helpers for screen-aware windows and readable long labels.

Tk does not provide a cross-platform backdrop blur, so these helpers affect
geometry and wrapping only. They keep the normal ttk keyboard traversal intact.
"""
import weakref


def configure_window(root, initial=(1080, 720), minimum=(480, 360), maximize=True):
    """Size a root window to the current display without exceeding its bounds.

    Call after creating ``Tk`` and before constructing the page. Tk uses device
    pixels after its own DPI scaling; this helper deliberately does not override
    Tk's scaling or mark the process DPI-aware behind the host application's back.
    """
    screen_width = max(1, root.winfo_screenwidth())
    screen_height = max(1, root.winfo_screenheight())
    width = min(initial[0], max(320, screen_width - 48))
    height = min(initial[1], max(280, screen_height - 72))
    min_width = min(max(320, minimum[0]), max(320, screen_width - 32))
    min_height = min(max(280, minimum[1]), max(280, screen_height - 72))
    # On a genuinely tiny virtual display, the minimum must never exceed the
    # initial geometry and force the window partly off screen.
    min_width = min(min_width, width)
    min_height = min(min_height, height)
    root.geometry(f'{width}x{height}')
    root.minsize(min_width, min_height)
    if maximize:
        try:
            root.state('zoomed')
        except Exception:
            # ``zoomed`` is not implemented on every Tk window manager.
            pass
    return width, height


def fit_dialog(dialog, root, size=(590, 390), minimum=(320, 280), margin=48):
    """Fit and center a dialog in the usable display area around the root."""
    screen_width = max(1, root.winfo_screenwidth())
    screen_height = max(1, root.winfo_screenheight())
    width = min(size[0], max(280, screen_width - margin))
    height = min(size[1], max(240, screen_height - margin * 2))
    min_width = min(minimum[0], width)
    min_height = min(minimum[1], height)
    try:
        x0, y0 = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = max(1, root.winfo_width()), max(1, root.winfo_height())
    except Exception:
        x0 = y0 = 0
        rw, rh = screen_width, screen_height
    x = max(0, min(screen_width - width, x0 + (rw - width) // 2))
    y = max(0, min(screen_height - height, y0 + (rh - height) // 2))
    dialog.geometry(f'{width}x{height}+{x}+{y}')
    dialog.minsize(min_width, min_height)
    try:
        dialog.transient(root)
    except Exception:
        pass
    return width, height


def bind_wraplength(root, label, inset=64, minimum=240, maximum=820):
    """Keep a Tk/ttk label's wrapping width inside its resized parent window."""
    targets = getattr(root, '_responsive_wrap_targets', None)
    if targets is None:
        targets = []
        root._responsive_wrap_targets = targets

        def update(event=None):
            width = event.width if event is not None else root.winfo_width()
            alive = []
            for reference, target_inset, target_minimum, target_maximum in targets:
                widget = reference()
                if widget is None:
                    continue
                try:
                    widget.configure(wraplength=max(
                        target_minimum, min(target_maximum, width - target_inset)))
                    alive.append((reference, target_inset, target_minimum, target_maximum))
                except Exception:
                    continue
            targets[:] = alive

        root._responsive_wrap_update = update
        root.bind('<Configure>', update, add='+')
    targets.append((weakref.ref(label), inset, minimum, maximum))
    root._responsive_wrap_update()
    return root._responsive_wrap_update
