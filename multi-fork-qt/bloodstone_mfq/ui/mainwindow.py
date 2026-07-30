"""Main window — multi-fork portfolio + per-coin wallet panels."""

from __future__ import annotations

import time
import traceback
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QRect, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QGuiApplication, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QDoubleSpinBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QSpinBox,
)

from .. import APP_NAME, __version__
from ..catalog import default_rpc_template, get_coin, list_coins
from ..daemon_manager import get_manager
from ..rpc import CoinRPC, fmt_amount
from .. import settings_store as store
from .styles import APP_STYLESHEET


class RefreshWorker(QThread):
    """Background refresh for all coins (non-blocking UI)."""

    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(
        self,
        conf_overrides: Dict[str, str],
        rpc_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.conf_overrides = conf_overrides
        self.rpc_overrides = rpc_overrides or {}

    def run(self):
        try:
            coins = list_coins(
                force=True,
                conf_overrides=self.conf_overrides,
                rpc_overrides=self.rpc_overrides,
            )
            rows = []
            for coin in coins:
                rpc = CoinRPC(coin)
                wallet = store.selected_wallet(coin["ticker"])
                info = rpc.get_info_bundle(wallet=wallet or None)
                rows.append({"coin": coin, "info": info, "wallet": wallet})
            self.finished_ok.emit(rows)
        except Exception as exc:
            self.failed.emit(f"{exc}\n{traceback.format_exc()}")


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — Multi-Fork Qt")
        self.setMinimumWidth(640)
        self.resize(720, 560)
        layout = QVBoxLayout(self)

        hint = QLabel(
            "Each coin needs local JSON-RPC credentials (rpcuser / rpcpassword / rpcport). "
            "On Windows these come from a local daemon conf — never from /root/… Linux paths. "
            "Use “Write conf templates” to create files under "
            f"{store.rpc_dir()} then paste the same rpcuser/rpcpassword as your node."
        )
        hint.setWordWrap(True)
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

        form = QFormLayout()
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(5, 600)
        self.refresh_spin.setSuffix(" s")
        self.refresh_spin.setValue(max(5, store.refresh_ms() // 1000))
        form.addRow("Auto-refresh interval", self.refresh_spin)
        layout.addLayout(form)

        conf_overrides = store.conf_overrides()
        rpc_ov = store.rpc_overrides()
        self.coin_fields: Dict[str, Dict[str, QLineEdit]] = {}

        conf_box = QGroupBox("Per-coin RPC (host / port / user / password / conf path)")
        conf_layout = QVBoxLayout(conf_box)

        for coin in list_coins(
            conf_overrides=conf_overrides, rpc_overrides=rpc_ov
        ):
            t = coin["ticker"]
            tpl = default_rpc_template(t)
            saved = rpc_ov.get(t) or {}
            box = QGroupBox(f"{t} — {coin.get('name') or t}")
            fl = QFormLayout(box)

            host = QLineEdit(
                str(
                    saved.get("rpc_host")
                    or coin.get("rpc_host")
                    or tpl["rpc_host"]
                )
            )
            port = QLineEdit(
                str(
                    saved.get("rpc_port")
                    or coin.get("rpc_port")
                    or tpl["rpc_port"]
                    or ""
                )
            )
            user = QLineEdit(
                str(saved.get("rpc_user") or coin.get("rpc_user") or tpl["rpc_user"])
            )
            password = QLineEdit(str(saved.get("rpc_password") or coin.get("rpc_password") or ""))
            password.setEchoMode(QLineEdit.Password)
            password.setPlaceholderText("same as your local daemon conf")

            conf_path = (
                conf_overrides.get(t)
                or saved.get("conf")
                or coin.get("conf")
                or tpl["conf_path"]
            )
            # Never pre-fill Linux operator paths
            if str(conf_path).startswith(("/root/", "/var/", "/home/")):
                conf_path = tpl["conf_path"]
            conf_edit = QLineEdit(str(conf_path or ""))
            conf_edit.setPlaceholderText(tpl["conf_path"])
            browse = QPushButton("…")
            browse.setFixedWidth(36)
            browse.setObjectName("secondaryBtn")
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(conf_edit, 1)
            hl.addWidget(browse)

            def _make_browse(e=conf_edit):
                def _go():
                    path, _ = QFileDialog.getOpenFileName(
                        self,
                        "Select conf",
                        e.text() or str(store.rpc_dir()),
                        "Conf (*.conf);;All (*)",
                    )
                    if path:
                        e.setText(path)

                return _go

            browse.clicked.connect(_make_browse())

            fl.addRow("Host", host)
            fl.addRow("Port", port)
            fl.addRow("rpcuser", user)
            fl.addRow("rpcpassword", password)
            fl.addRow("Conf file", row)
            conf_layout.addWidget(box)
            self.coin_fields[t] = {
                "host": host,
                "port": port,
                "user": user,
                "password": password,
                "conf": conf_edit,
            }

        layout.addWidget(conf_box)

        btn_row = QHBoxLayout()
        self.btn_templates = QPushButton("Write conf templates")
        self.btn_templates.setObjectName("secondaryBtn")
        self.btn_templates.setToolTip(
            "Create local conf files under MultiForkQt/rpc and fill credentials from the fields above"
        )
        self.btn_templates.clicked.connect(self._write_templates)
        btn_row.addWidget(self.btn_templates)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _write_templates(self):
        written = []
        for t, fields in self.coin_fields.items():
            try:
                port = int(fields["port"].text().strip() or "0")
            except ValueError:
                port = 0
            path = store.write_conf_template(
                t,
                rpc_user=fields["user"].text().strip(),
                rpc_password=fields["password"].text().strip(),
                rpc_port=port,
                rpc_host=fields["host"].text().strip() or "127.0.0.1",
                path=fields["conf"].text().strip() or "",
            )
            fields["conf"].setText(path)
            written.append(f"{t}: {path}")
        QMessageBox.information(
            self,
            "Templates written",
            "Wrote conf templates:\n\n"
            + "\n".join(written)
            + "\n\nEdit rpcpassword if still CHANGE_ME, and ensure the matching "
            "local daemon is running (bloodstoned / azured / lrgkd).",
        )

    def apply(self):
        store.set_refresh_ms(self.refresh_spin.value() * 1000)
        conf_map: Dict[str, str] = {}
        rpc_map: Dict[str, Dict[str, Any]] = {}
        for t, fields in self.coin_fields.items():
            conf = fields["conf"].text().strip()
            if conf and not conf.startswith(("/root/", "/var/", "/home/")):
                conf_map[t] = conf
            entry: Dict[str, Any] = {}
            if fields["host"].text().strip():
                entry["rpc_host"] = fields["host"].text().strip()
            if fields["port"].text().strip():
                try:
                    entry["rpc_port"] = int(fields["port"].text().strip())
                except ValueError:
                    pass
            if fields["user"].text().strip():
                entry["rpc_user"] = fields["user"].text().strip()
            if fields["password"].text().strip():
                entry["rpc_password"] = fields["password"].text().strip()
            if conf and not conf.startswith(("/root/", "/var/", "/home/")):
                entry["conf"] = conf
            if entry:
                rpc_map[t] = entry
        store.set_conf_overrides(conf_map)
        store.set_rpc_overrides(rpc_map)


class CreateWalletDialog(QDialog):
    """Create a new named wallet on the local daemon (Qt-compatible legacy)."""

    def __init__(self, ticker: str, parent=None):
        super().__init__(parent)
        self.ticker = (ticker or "STONE").upper()
        self.result_data: Optional[Dict[str, Any]] = None
        self.setWindowTitle(f"Create wallet — {self.ticker}")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        intro = QLabel(
            f"Create a new wallet on the <b>{self.ticker}</b> local daemon. "
            "Uses a legacy wallet so you can export WIF and import into Core Qt. "
            "Start the daemon first if the coin is offline."
        )
        intro.setWordWrap(True)
        intro.setObjectName("mutedLabel")
        layout.addWidget(intro)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. mywallet or cold1")
        self.name_edit.setText(f"mfq{self.ticker.lower()}")
        form.addRow("Wallet name", self.name_edit)

        self.encrypt_chk = QCheckBox("Encrypt with passphrase (recommended)")
        self.encrypt_chk.setChecked(True)
        form.addRow(self.encrypt_chk)

        self.pp_edit = QLineEdit()
        self.pp_edit.setEchoMode(QLineEdit.Password)
        self.pp_edit.setPlaceholderText("Min 8 characters")
        form.addRow("Passphrase", self.pp_edit)

        self.pp2_edit = QLineEdit()
        self.pp2_edit.setEchoMode(QLineEdit.Password)
        self.pp2_edit.setPlaceholderText("Repeat passphrase")
        form.addRow("Confirm", self.pp2_edit)
        layout.addLayout(form)

        hint = QLabel(
            "If you encrypt, keys are generated after encryption (correct HD seed). "
            "Save the WIF backup when the dialog finishes."
        )
        hint.setWordWrap(True)
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Create wallet")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Create wallet", "Enter a wallet name.")
            return
        pp = ""
        if self.encrypt_chk.isChecked():
            pp = self.pp_edit.text()
            pp2 = self.pp2_edit.text()
            if len(pp) < 8:
                QMessageBox.warning(
                    self, "Create wallet", "Passphrase must be at least 8 characters."
                )
                return
            if pp != pp2:
                QMessageBox.warning(self, "Create wallet", "Passphrases do not match.")
                return
        self._wallet_name = name
        self._passphrase = pp
        self.accept()

    def values(self) -> tuple:
        return (
            getattr(self, "_wallet_name", self.name_edit.text().strip()),
            getattr(self, "_passphrase", ""),
        )


class WalletCreatedDialog(QDialog):
    """Show address + WIF and offer .md backup save."""

    def __init__(self, data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle(f"Wallet created — {data.get('ticker', '')}")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(
                f"<b>{data.get('ticker')}</b> wallet <code>{data.get('name')}</code> "
                f"{'encrypted' if data.get('encrypted') else 'unencrypted'}"
            )
        )

        form = QFormLayout()
        addr = QLineEdit(data.get("address") or "")
        addr.setReadOnly(True)
        form.addRow("Address", addr)
        wif = QLineEdit(data.get("wif") or "")
        wif.setReadOnly(True)
        form.addRow("WIF", wif)
        layout.addLayout(form)

        warn = QLabel(
            "Anyone with the WIF can spend funds. Save offline, then clear this screen."
        )
        warn.setObjectName("mutedLabel")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        row = QHBoxLayout()
        btn_copy_a = QPushButton("Copy address")
        btn_copy_a.setObjectName("secondaryBtn")
        btn_copy_a.clicked.connect(
            lambda: QApplication.clipboard().setText(data.get("address") or "")
        )
        row.addWidget(btn_copy_a)
        btn_copy_w = QPushButton("Copy WIF")
        btn_copy_w.setObjectName("secondaryBtn")
        btn_copy_w.clicked.connect(
            lambda: QApplication.clipboard().setText(data.get("wif") or "")
        )
        row.addWidget(btn_copy_w)
        btn_md = QPushButton("Save backup .md…")
        btn_md.clicked.connect(self._save_md)
        row.addWidget(btn_md)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

    def _save_md(self):
        d = self.data
        ticker = d.get("ticker") or "COIN"
        default = str(
            store.config_dir()
            / f"{ticker.lower()}-wallet-{d.get('name') or 'wallet'}-backup.md"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save wallet backup",
            default,
            "Markdown (*.md);;All (*)",
        )
        if not path:
            return
        import time as _time

        ts = _time.strftime("%Y-%m-%d %H:%M:%S UTC", _time.gmtime())
        md = "\n".join(
            [
                f"# {ticker} wallet backup (Multi-Fork Qt)",
                "",
                f"- **Created:** {ts}",
                f"- **Wallet name:** `{d.get('name')}`",
                f"- **Encrypted:** {'yes' if d.get('encrypted') else 'no'}",
                "",
                "## Receive address",
                "",
                f"`{d.get('address')}`",
                "",
                "## Private key (WIF)",
                "",
                f"`{d.get('wif')}`",
                "",
                "## Import",
                "",
                "```",
                f'importprivkey "{d.get("wif")}" "primary" false',
                "```",
                "",
                "## Security",
                "",
                "- Anyone with this WIF can spend your funds.",
                "- Store offline and delete the file after saving elsewhere.",
                "",
            ]
        )
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(md)
            QMessageBox.information(self, "Saved", f"Wrote:\n{path}")
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))


def _available_screen_rect() -> QRect:
    """Usable desktop area for the primary (or current) screen."""
    app = QApplication.instance()
    screen = None
    if app is not None:
        try:
            screen = app.primaryScreen()
        except Exception:
            screen = None
    if screen is None:
        try:
            screen = QGuiApplication.primaryScreen()
        except Exception:
            screen = None
    if screen is not None:
        return screen.availableGeometry()
    return QRect(0, 0, 1280, 800)


def fit_window_size(
    preferred_w: int = 960,
    preferred_h: int = 640,
    *,
    min_w: int = 760,
    min_h: int = 520,
    max_frac: float = 0.92,
) -> QSize:
    """Default size that fits on-screen (avoids ultra-wide / off-screen launches)."""
    geo = _available_screen_rect()
    max_w = max(min_w, int(geo.width() * max_frac))
    max_h = max(min_h, int(geo.height() * max_frac))
    w = min(preferred_w, max_w)
    h = min(preferred_h, max_h)
    # Keep a normal landscape ratio — never force ~3× screen width content
    if w > h * 1.85:
        w = int(h * 1.75)
    w = max(min_w, min(w, max_w))
    h = max(min_h, min(h, max_h))
    return QSize(w, h)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.setStyleSheet(APP_STYLESHEET)
        # Hard floor so widgets cannot inflate the frame to multi-screen widths
        self.setMinimumSize(760, 520)
        size = fit_window_size(960, 640)
        self.resize(size)
        self.setMaximumSize(16777215, 16777215)  # Qt default; explicit for clarity

        self._rows: List[Dict[str, Any]] = []
        self._current_ticker = store.last_ticker() or "STONE"
        self._worker: Optional[RefreshWorker] = None
        self._busy = False
        self._daemon_busy = False
        self._mgr = get_manager()
        self._mgr.set_log(lambda m: self._status.showMessage(m, 8000) if hasattr(self, "_status") else None)

        self._build_menu()
        self._build_ui()
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._mgr.set_log(lambda m: self._status.showMessage(str(m)[:200], 10000))
        self._status.showMessage("Loading fork catalogue…")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_all)
        self._timer.start(store.refresh_ms())

        QTimer.singleShot(0, self._clamp_to_screen)
        QTimer.singleShot(100, self.refresh_all)
        QTimer.singleShot(200, self._init_daemon_runtime)

    def _clamp_to_screen(self) -> None:
        """Center and ensure the frame is fully on the available desktop."""
        geo = _available_screen_rect()
        # Re-fit if still oversized (DPI / late screen metrics)
        frame = self.frameGeometry()
        max_w = max(760, int(geo.width() * 0.94))
        max_h = max(520, int(geo.height() * 0.94))
        w = min(self.width(), max_w)
        h = min(self.height(), max_h)
        if w != self.width() or h != self.height():
            self.resize(w, h)
        # Center on available geometry
        x = geo.x() + max(0, (geo.width() - self.width()) // 2)
        y = geo.y() + max(0, (geo.height() - self.height()) // 2)
        self.move(x, y)

    # ── chrome ─────────────────────────────────────────────
    def _build_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        act_refresh = QAction("Refresh", self)
        act_refresh.setShortcut(QKeySequence.Refresh)
        act_refresh.triggered.connect(self.refresh_all)
        file_menu.addAction(act_refresh)

        act_settings = QAction("Settings…", self)
        act_settings.triggered.connect(self.open_settings)
        file_menu.addAction(act_settings)
        file_menu.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(act_quit)

        wallet_menu = self.menuBar().addMenu("&Wallet")
        act_new_w = QAction("Create new wallet…", self)
        act_new_w.setShortcut("Ctrl+N")
        act_new_w.triggered.connect(self.create_wallet)
        wallet_menu.addAction(act_new_w)
        act_unlock = QAction("Unlock wallet…", self)
        act_unlock.triggered.connect(self.unlock_wallet)
        wallet_menu.addAction(act_unlock)

        node_menu = self.menuBar().addMenu("&Node")
        act_start = QAction("Start local daemon for selected coin", self)
        act_start.triggered.connect(self.start_local_daemon)
        node_menu.addAction(act_start)
        act_stop = QAction("Stop local daemon for selected coin", self)
        act_stop.triggered.connect(self.stop_local_daemon)
        node_menu.addAction(act_stop)
        act_stop_all = QAction("Stop all local daemons", self)
        act_stop_all.triggered.connect(self.stop_all_daemons)
        node_menu.addAction(act_stop_all)

        help_menu = self.menuBar().addMenu("&Help")
        act_about = QAction("About", self)
        act_about.triggered.connect(self.show_about)
        help_menu.addAction(act_about)

    def _build_ui(self):
        root = QWidget()
        root.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter)

        # Left: coin list (capped width so long labels cannot stretch the window)
        left = QWidget()
        left.setMinimumWidth(200)
        left.setMaximumWidth(340)
        left.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Chains & forks")
        title.setObjectName("titleLabel")
        left_l.addWidget(title)
        sub = QLabel("STONE + every live Fork Lab coin")
        sub.setObjectName("mutedLabel")
        sub.setWordWrap(True)
        left_l.addWidget(sub)

        self.coin_list = QListWidget()
        self.coin_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.coin_list.setTextElideMode(Qt.ElideRight)
        self.coin_list.setUniformItemSizes(False)
        self.coin_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.coin_list.currentItemChanged.connect(self._on_coin_selected)
        left_l.addWidget(self.coin_list, 1)

        self.portfolio_label = QLabel("Portfolio loading…")
        self.portfolio_label.setObjectName("mutedLabel")
        self.portfolio_label.setWordWrap(True)
        self.portfolio_label.setMaximumHeight(120)
        left_l.addWidget(self.portfolio_label)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("secondaryBtn")
        self.btn_refresh.clicked.connect(self.refresh_all)
        btn_row.addWidget(self.btn_refresh)
        left_l.addLayout(btn_row)

        splitter.addWidget(left)

        # Right: detail tabs
        right = QWidget()
        right.setMinimumWidth(420)
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)

        hdr = QHBoxLayout()
        self.coin_title = QLabel("Select a coin")
        self.coin_title.setObjectName("titleLabel")
        self.coin_title.setWordWrap(True)
        hdr.addWidget(self.coin_title, 1)
        self.online_label = QLabel("")
        hdr.addWidget(self.online_label)
        right_l.addLayout(hdr)

        self.balance_label = QLabel("—")
        self.balance_label.setObjectName("balanceLabel")
        self.balance_label.setWordWrap(True)
        right_l.addWidget(self.balance_label)

        meta = QHBoxLayout()
        self.height_label = QLabel("")
        self.height_label.setObjectName("mutedLabel")
        self.height_label.setWordWrap(True)
        self.height_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        meta.addWidget(self.height_label, 1)
        meta.addWidget(QLabel("Wallet:"))
        self.wallet_combo = QComboBox()
        self.wallet_combo.setMinimumWidth(120)
        self.wallet_combo.setMaximumWidth(220)
        self.wallet_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.wallet_combo.setMinimumContentsLength(8)
        self.wallet_combo.currentTextChanged.connect(self._on_wallet_changed)
        meta.addWidget(self.wallet_combo)
        self.btn_new_wallet = QPushButton("New wallet…")
        self.btn_new_wallet.setToolTip(
            "Create a new named wallet on the local daemon (Ctrl+N)"
        )
        self.btn_new_wallet.clicked.connect(self.create_wallet)
        meta.addWidget(self.btn_new_wallet)
        self.btn_unlock = QPushButton("Unlock…")
        self.btn_unlock.setObjectName("secondaryBtn")
        self.btn_unlock.clicked.connect(self.unlock_wallet)
        meta.addWidget(self.btn_unlock)
        right_l.addLayout(meta)

        # Local daemon controls (download on select + start/stop)
        daemon_box = QGroupBox("Local node (per selected fork)")
        daemon_l = QVBoxLayout(daemon_box)
        self.daemon_status = QLabel("Daemon: —")
        self.daemon_status.setObjectName("mutedLabel")
        self.daemon_status.setWordWrap(True)
        daemon_l.addWidget(self.daemon_status)
        self.daemon_progress = QLabel("")
        self.daemon_progress.setObjectName("mutedLabel")
        daemon_l.addWidget(self.daemon_progress)
        drow = QHBoxLayout()
        self.chk_auto_daemon = QPushButton("Auto-start on select: ON")
        self.chk_auto_daemon.setCheckable(True)
        self.chk_auto_daemon.setChecked(True)
        self.chk_auto_daemon.setObjectName("secondaryBtn")
        self.chk_auto_daemon.clicked.connect(self._toggle_auto_daemon)
        drow.addWidget(self.chk_auto_daemon)
        self.btn_daemon_start = QPushButton("Download & start daemon")
        self.btn_daemon_start.clicked.connect(self.start_local_daemon)
        drow.addWidget(self.btn_daemon_start)
        self.btn_daemon_stop = QPushButton("Stop daemon")
        self.btn_daemon_stop.setObjectName("secondaryBtn")
        self.btn_daemon_stop.clicked.connect(self.stop_local_daemon)
        drow.addWidget(self.btn_daemon_stop)
        drow.addStretch(1)
        daemon_l.addLayout(drow)
        right_l.addWidget(daemon_box)

        self.tabs = QTabWidget()
        right_l.addWidget(self.tabs, 1)

        # Overview
        ov = QWidget()
        ov_l = QVBoxLayout(ov)
        self.overview_text = QPlainTextEdit()
        self.overview_text.setReadOnly(True)
        self.overview_text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.overview_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.overview_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ov_l.addWidget(self.overview_text)
        self.tabs.addTab(ov, "Overview")

        # Receive
        recv = QWidget()
        recv_l = QVBoxLayout(recv)
        self.recv_address = QLineEdit()
        self.recv_address.setReadOnly(True)
        self.recv_address.setPlaceholderText("Click Generate for a new address")
        recv_l.addWidget(QLabel("Receive address"))
        recv_l.addWidget(self.recv_address)
        rb = QHBoxLayout()
        self.btn_new_addr = QPushButton("Generate new address")
        self.btn_new_addr.clicked.connect(self.generate_address)
        rb.addWidget(self.btn_new_addr)
        self.btn_copy_addr = QPushButton("Copy")
        self.btn_copy_addr.setObjectName("secondaryBtn")
        self.btn_copy_addr.clicked.connect(self.copy_address)
        rb.addWidget(self.btn_copy_addr)
        rb.addStretch(1)
        recv_l.addLayout(rb)
        recv_l.addStretch(1)
        self.tabs.addTab(recv, "Receive")

        # Send
        send = QWidget()
        send_l = QVBoxLayout(send)
        form = QFormLayout()
        self.send_to = QLineEdit()
        self.send_to.setPlaceholderText("Destination address")
        self.send_amount = QDoubleSpinBox()
        self.send_amount.setDecimals(8)
        self.send_amount.setMaximum(1e12)
        self.send_amount.setSingleStep(0.1)
        self.send_comment = QLineEdit()
        self.send_comment.setPlaceholderText("Optional comment")
        form.addRow("To", self.send_to)
        form.addRow("Amount", self.send_amount)
        form.addRow("Comment", self.send_comment)
        send_l.addLayout(form)
        self.btn_send = QPushButton("Send")
        self.btn_send.setObjectName("dangerBtn")
        self.btn_send.clicked.connect(self.send_coins)
        send_l.addWidget(self.btn_send, 0, Qt.AlignLeft)
        send_l.addStretch(1)
        self.tabs.addTab(send, "Send")

        # History
        hist = QWidget()
        hist_l = QVBoxLayout(hist)
        self.tx_table = QTableWidget(0, 5)
        self.tx_table.setHorizontalHeaderLabels(
            ["Time", "Category", "Amount", "Confirmations", "TxID"]
        )
        hdr_view = self.tx_table.horizontalHeader()
        hdr_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr_view.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr_view.setStretchLastSection(True)
        self.tx_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.tx_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tx_table.setTextElideMode(Qt.ElideMiddle)
        self.tx_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tx_table.setWordWrap(False)
        self.tx_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        hist_l.addWidget(self.tx_table)
        self.btn_hist = QPushButton("Reload history")
        self.btn_hist.setObjectName("secondaryBtn")
        self.btn_hist.clicked.connect(self.load_history)
        hist_l.addWidget(self.btn_hist, 0, Qt.AlignLeft)
        self.tabs.addTab(hist, "History")

        # Console
        cons = QWidget()
        cons_l = QVBoxLayout(cons)
        self.console_out = QPlainTextEdit()
        self.console_out.setReadOnly(True)
        self.console_out.setFont(QFont("Monospace", 10))
        self.console_out.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.console_out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cons_l.addWidget(self.console_out, 1)
        row = QHBoxLayout()
        self.console_in = QLineEdit()
        self.console_in.setPlaceholderText('RPC method [json-params]  e.g. getblockchaininfo  or  getbalance ["*",0]')
        self.console_in.returnPressed.connect(self.run_console)
        row.addWidget(self.console_in, 1)
        self.btn_console = QPushButton("Call")
        self.btn_console.clicked.connect(self.run_console)
        row.addWidget(self.btn_console)
        cons_l.addLayout(row)
        self.tabs.addTab(cons, "Console")

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        # Proportional start: ~26% list / 74% detail (not a fixed 1180px total)
        total = max(700, self.width() - 20)
        left_w = min(280, max(220, int(total * 0.26)))
        splitter.setSizes([left_w, max(420, total - left_w)])
        self._splitter = splitter

    # ── data ───────────────────────────────────────────────
    def conf_overrides(self) -> Dict[str, str]:
        return store.conf_overrides()

    def rpc_overrides(self) -> Dict[str, Dict[str, Any]]:
        return store.rpc_overrides()

    def refresh_all(self):
        if self._busy:
            return
        self._busy = True
        self.btn_refresh.setEnabled(False)
        self._status.showMessage("Refreshing all forks…")
        self._worker = RefreshWorker(
            self.conf_overrides(), self.rpc_overrides(), self
        )
        self._worker.finished_ok.connect(self._on_refresh_ok)
        self._worker.failed.connect(self._on_refresh_fail)
        self._worker.start()

    def _on_refresh_ok(self, rows: list):
        self._rows = rows
        self._busy = False
        self.btn_refresh.setEnabled(True)
        self._rebuild_coin_list()
        self._update_portfolio()
        self._show_coin(self._current_ticker)
        online = sum(1 for r in rows if (r.get("info") or {}).get("probe", {}).get("online"))
        self._status.showMessage(
            f"Updated {time.strftime('%H:%M:%S')} — {online}/{len(rows)} chains online"
        )
        self._timer.setInterval(store.refresh_ms())

    def _on_refresh_fail(self, err: str):
        self._busy = False
        self.btn_refresh.setEnabled(True)
        self._status.showMessage("Refresh failed")
        QMessageBox.warning(self, "Refresh failed", err[:800])

    def _rebuild_coin_list(self):
        current = self._current_ticker
        self.coin_list.blockSignals(True)
        self.coin_list.clear()
        for row in self._rows:
            coin = row["coin"]
            info = row["info"]
            probe = info.get("probe") or {}
            online = bool(probe.get("online"))
            bal = info.get("balance")
            bal_s = fmt_amount(bal) if bal is not None else "—"
            mark = "●" if online else "○"
            label = f"{mark}  {coin['ticker']}\n    {coin['name']}  ·  {bal_s}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, coin["ticker"])
            tip = []
            if probe.get("blocks") is not None:
                tip.append(f"Height {probe['blocks']}")
            if probe.get("error"):
                tip.append(probe["error"])
            peers = coin.get("public_peers") or (
                [coin["public_peer"]] if coin.get("public_peer") else []
            )
            if peers:
                tip.append("Seeds " + ", ".join(str(p) for p in peers))
            item.setToolTip("\n".join(tip) or coin.get("description") or "")
            self.coin_list.addItem(item)
            if coin["ticker"] == current:
                self.coin_list.setCurrentItem(item)
        if self.coin_list.currentRow() < 0 and self.coin_list.count():
            self.coin_list.setCurrentRow(0)
        self.coin_list.blockSignals(False)

    def _update_portfolio(self):
        lines = []
        for row in self._rows:
            coin = row["coin"]
            bal = (row.get("info") or {}).get("balance")
            online = (row.get("info") or {}).get("probe", {}).get("online")
            if bal is None:
                continue
            lines.append(f"{coin['ticker']}: {fmt_amount(bal)}" + ("" if online else " (offline)"))
        if lines:
            self.portfolio_label.setText("Balances\n" + "\n".join(lines))
        else:
            self.portfolio_label.setText("No balances yet — configure RPC confs in Settings.")

    def _row_for(self, ticker: str) -> Optional[Dict[str, Any]]:
        t = (ticker or "").upper()
        for r in self._rows:
            if r["coin"]["ticker"] == t:
                return r
        return None

    def _on_coin_selected(self, cur: QListWidgetItem, _prev):
        if not cur:
            return
        ticker = cur.data(Qt.UserRole)
        if ticker:
            self._current_ticker = ticker
            store.set_last_ticker(ticker)
            self._show_coin(ticker)
            self._update_daemon_status()
            if self.chk_auto_daemon.isChecked():
                QTimer.singleShot(150, self.start_local_daemon)

    def _show_coin(self, ticker: str):
        row = self._row_for(ticker)
        if not row:
            # not yet refreshed — show catalog only
            coin = get_coin(
                ticker,
                conf_overrides=self.conf_overrides(),
                rpc_overrides=self.rpc_overrides(),
            )
            if not coin:
                return
            self.coin_title.setText(f"{coin['ticker']} — {coin['name']}")
            self.balance_label.setText("—")
            self.online_label.setText("Unknown")
            self.online_label.setObjectName("offlineDot")
            self.online_label.setStyle(self.online_label.style())
            return

        coin = row["coin"]
        info = row["info"]
        probe = info.get("probe") or {}
        online = bool(probe.get("online"))

        self.coin_title.setText(f"{coin['ticker']} — {coin['name']}")
        bal = info.get("balance")
        unit = coin["ticker"]
        self.balance_label.setText(
            f"{fmt_amount(bal)} {unit}" if bal is not None else f"— {unit}"
        )
        if online:
            self.online_label.setText("● Online")
            self.online_label.setStyleSheet("color: #3dce7a; font-weight: 700;")
        else:
            self.online_label.setText("○ Offline")
            self.online_label.setStyleSheet("color: #e06060; font-weight: 700;")

        height = probe.get("blocks")
        chain = probe.get("chain") or ""
        err = probe.get("error") or info.get("balance_error") or ""
        bits = []
        if height is not None:
            bits.append(f"Height {height}")
        if chain:
            bits.append(chain)
        peers = coin.get("public_peers") or (
            [coin["public_peer"]] if coin.get("public_peer") else []
        )
        if peers:
            bits.append("seeds " + ", ".join(str(p) for p in peers))
        if err and not online:
            bits.append(err)
        self.height_label.setText(" · ".join(bits))

        # wallets
        self.wallet_combo.blockSignals(True)
        self.wallet_combo.clear()
        wallets = info.get("wallets") or [""]
        if not wallets:
            wallets = [""]
        for w in wallets:
            self.wallet_combo.addItem(w if w else "(default)")
        preferred = row.get("wallet") or store.selected_wallet(coin["ticker"])
        if preferred:
            idx = self.wallet_combo.findText(preferred)
            if idx < 0 and preferred:
                self.wallet_combo.addItem(preferred)
                idx = self.wallet_combo.findText(preferred)
            if idx >= 0:
                self.wallet_combo.setCurrentIndex(idx)
        self.wallet_combo.blockSignals(False)

        # overview
        ov_lines = [
            f"Ticker:     {coin['ticker']}",
            f"Name:       {coin['name']}",
            f"Fork ID:    {coin.get('fork_id') or '—'}",
            f"Status:     {coin.get('status')}",
            f"Source:     {coin.get('source')}",
            f"P2P port:   {coin.get('p2p_port') or '—'}",
            f"RPC port:   {coin.get('rpc_port') or '—'}",
            f"RPC host:   {info.get('rpc_host') or coin.get('rpc_host')}",
            f"RPC port:   {info.get('rpc_port') or coin.get('rpc_port') or '—'}",
            f"Conf:       {info.get('conf_path') or coin.get('conf') or '—'}",
            f"Conf ready: {coin.get('has_conf')}",
            f"Configured: {info.get('configured')}",
            f"Seeds:      {', '.join(coin.get('public_peers') or ([coin['public_peer']] if coin.get('public_peer') else [])) or '—'}",
            f"Description:{coin.get('description') or '—'}",
            "",
            f"Online:     {online}",
            f"Height:     {height}",
            f"Chain:      {chain}",
            f"Balance:    {fmt_amount(bal)} {coin['ticker']}",
            f"Wallets:    {', '.join(wallets) if wallets else '—'}",
        ]
        if err:
            ov_lines.append(f"Error:      {err}")
        cands = coin.get("conf_candidates") or []
        if cands and not coin.get("has_conf"):
            ov_lines.append("")
            ov_lines.append("Conf search paths (create one or set in Settings):")
            for p in cands[:8]:
                ov_lines.append(f"  · {p}")
        self.overview_text.setPlainText("\n".join(ov_lines))

        if online:
            self.load_history()
        self._update_daemon_status()

    def _current_rpc(self) -> Optional[CoinRPC]:
        row = self._row_for(self._current_ticker)
        if not row:
            coin = get_coin(
                self._current_ticker,
                conf_overrides=self.conf_overrides(),
                rpc_overrides=self.rpc_overrides(),
            )
            if not coin:
                return None
            return CoinRPC(coin)
        return CoinRPC(row["coin"])

    def _current_wallet_name(self) -> Optional[str]:
        text = self.wallet_combo.currentText()
        if not text or text == "(default)":
            return None
        return text

    def _on_wallet_changed(self, text: str):
        if not self._current_ticker:
            return
        name = "" if not text or text == "(default)" else text
        store.set_selected_wallet(self._current_ticker, name)
        # soft balance refresh for this coin
        try:
            rpc = self._current_rpc()
            if not rpc:
                return
            if name:
                try:
                    rpc.load_wallet(name)
                except Exception:
                    pass
            bal = rpc.balance(wallet=name or None)
            self.balance_label.setText(f"{fmt_amount(bal)} {self._current_ticker}")
        except Exception:
            pass

    # ── actions ────────────────────────────────────────────
    def generate_address(self):
        rpc = self._current_rpc()
        if not rpc:
            return
        wallet = self._current_wallet_name()
        try:
            # Multiwallet nodes require an explicit wallet; resolve one when
            # the combo still says (default) / empty.
            use = rpc.resolve_wallet_for_rpc(wallet)
            if use is None and not rpc.list_wallets() and not rpc.list_wallet_dir():
                QMessageBox.information(
                    self,
                    "No wallet yet",
                    f"No {self._current_ticker} wallet is loaded.\n\n"
                    "Use Create wallet first (modern nodes no longer auto-create "
                    "a default wallet), then generate a receive address.",
                )
                return
            # Prefer legacy (S…/L…/A…) and reject wrong-chain daemon addresses
            addr = rpc.new_address(
                wallet=use, label="mfq", address_type="legacy", validate=True
            )
            self.recv_address.setText(addr)
            self._status.showMessage(
                f"New {self._current_ticker} address generated (legacy P2PKH)"
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Address failed",
                str(exc)
                + "\n\nIf this mentions Bloodstone/STONE while you selected a fork, "
                "the Windows daemon pack is the wrong binary — need a real "
                f"{self._current_ticker} node, not renamed bloodstoned.exe.",
            )

    def copy_address(self):
        addr = self.recv_address.text().strip()
        if not addr:
            return
        QApplication.clipboard().setText(addr)
        self._status.showMessage("Address copied to clipboard")

    def send_coins(self):
        rpc = self._current_rpc()
        if not rpc:
            return
        to = self.send_to.text().strip()
        amount = float(self.send_amount.value())
        comment = self.send_comment.text().strip()
        if not to or amount <= 0:
            QMessageBox.warning(self, "Send", "Enter a destination address and amount > 0.")
            return
        wallet = self._current_wallet_name()
        reply = QMessageBox.question(
            self,
            "Confirm send",
            f"Send {fmt_amount(amount)} {self._current_ticker} to:\n{to}\n\nWallet: {wallet or '(default)'}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if wallet:
                rpc.load_wallet(wallet)
            txid = rpc.send(to, amount, wallet=wallet, comment=comment)
            QMessageBox.information(self, "Sent", f"Transaction broadcast.\n\nTxID:\n{txid}")
            self.send_to.clear()
            self.send_amount.setValue(0)
            self.load_history()
            self.refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, "Send failed", str(exc))

    def unlock_wallet(self):
        rpc = self._current_rpc()
        if not rpc:
            return
        pw, ok = QInputDialog.getText(
            self, "Unlock wallet", "Passphrase:", QLineEdit.Password
        )
        if not ok or not pw:
            return
        wallet = self._current_wallet_name()
        try:
            if wallet:
                rpc.load_wallet(wallet)
            rpc.unlock(pw, 600, wallet=wallet)
            self._status.showMessage("Wallet unlocked for 10 minutes")
        except Exception as exc:
            QMessageBox.warning(self, "Unlock failed", str(exc))

    def create_wallet(self):
        """Create a new wallet on the active coin's local daemon."""
        ticker = self._current_ticker
        if not ticker:
            QMessageBox.information(
                self, "Create wallet", "Select a coin in the list first."
            )
            return
        rpc = self._current_rpc()
        if not rpc:
            QMessageBox.warning(self, "Create wallet", "No RPC client for this coin.")
            return
        if not rpc.configured:
            QMessageBox.warning(
                self,
                "Create wallet",
                rpc.config_hint()
                + "\n\nStart the local daemon (Download & start) or set RPC in Settings.",
            )
            return
        probe = rpc.probe(timeout=3.0)
        if not probe.get("online"):
            reply = QMessageBox.question(
                self,
                "Daemon offline",
                f"{ticker} RPC is offline ({probe.get('error') or 'no response'}).\n\n"
                "Start the local daemon now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.start_local_daemon()
            return

        # Refuse wrong-chain daemons (renamed bloodstoned → STONE addresses)
        if self._mgr.is_placeholder_fork_binary(ticker):
            QMessageBox.critical(
                self,
                "Wrong daemon binary",
                f"The installed {ticker} Windows node pack is a renamed Bloodstone "
                f"binary. It only creates STONE addresses (S… / stone1…), which are "
                f"invalid for {ticker}.\n\n"
                f"Fix: run a real {ticker} daemon and set its RPC in Settings, "
                f"or wait for a true {ticker} win64 node pack.",
            )
            return
        # Pre-check only when a wallet already exists (can mint a sample
        # address). Fresh multiwallet nodes have no default wallet — identity
        # is verified on the first address after createwallet instead.
        try:
            rpc.assert_chain_identity(wallet=self._current_wallet_name())
        except Exception as exc:
            msg = str(exc)
            low = msg.lower()
            if (
                "no wallet is loaded" in low
                or "wallet file not specified" in low
                or "must request wallet rpc" in low
            ):
                pass  # expected on first-run; create_wallet re-validates
            else:
                QMessageBox.critical(
                    self,
                    "Chain identity check failed",
                    msg[:800]
                    + "\n\nWallet creation aborted to avoid minting unusable addresses.",
                )
                return

        dlg = CreateWalletDialog(ticker, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        name, passphrase = dlg.values()
        self._status.showMessage(f"Creating wallet {name} on {ticker}…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            data = rpc.create_wallet(name, passphrase=passphrase)
            data["ticker"] = ticker
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Create wallet failed", str(exc)[:800])
            self._status.showMessage("Create wallet failed")
            return
        QApplication.restoreOverrideCursor()

        # Select new wallet in combo and persist
        store.set_selected_wallet(ticker, name)
        # Refresh list then select
        self.refresh_all()
        # Ensure combo has the new name even before refresh finishes
        if self.wallet_combo.findText(name) < 0:
            self.wallet_combo.addItem(name)
        self.wallet_combo.setCurrentText(name)

        self._status.showMessage(
            f"Created {ticker} wallet “{name}” — address {data.get('address', '')[:20]}…"
        )
        # Show WIF / backup dialog
        result_dlg = WalletCreatedDialog(data, self)
        result_dlg.exec_()
        # Refresh again for balances after dialog
        QTimer.singleShot(500, self.refresh_all)

    def load_history(self):
        rpc = self._current_rpc()
        if not rpc:
            return
        wallet = self._current_wallet_name()
        self.tx_table.setRowCount(0)
        try:
            if wallet:
                try:
                    rpc.load_wallet(wallet)
                except Exception:
                    pass
            txs = rpc.list_transactions(wallet=wallet, count=80)
        except Exception as exc:
            self._status.showMessage(f"History: {exc}")
            return

        self.tx_table.setRowCount(len(txs))
        for i, tx in enumerate(txs):
            ts = tx.get("time") or tx.get("timereceived") or 0
            try:
                tstr = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))
            except Exception:
                tstr = str(ts)
            vals = [
                tstr,
                str(tx.get("category") or ""),
                fmt_amount(tx.get("amount")),
                str(tx.get("confirmations", "")),
                str(tx.get("txid") or ""),
            ]
            for j, v in enumerate(vals):
                self.tx_table.setItem(i, j, QTableWidgetItem(v))

    def run_console(self):
        rpc = self._current_rpc()
        if not rpc:
            return
        line = self.console_in.text().strip()
        if not line:
            return
        import json
        import shlex

        wallet = self._current_wallet_name()
        # parse: method optional-json-array
        parts = line.split(None, 1)
        method = parts[0]
        params: List[Any] = []
        if len(parts) > 1:
            rest = parts[1].strip()
            try:
                parsed = json.loads(rest)
                if isinstance(parsed, list):
                    params = parsed
                else:
                    params = [parsed]
            except json.JSONDecodeError:
                # space-separated tokens
                try:
                    params = shlex.split(rest)
                except ValueError:
                    params = [rest]
        self.console_out.appendPlainText(f">>> {line}")
        try:
            if wallet and method not in (
                "listwallets",
                "loadwallet",
                "getblockchaininfo",
                "getnetworkinfo",
                "getpeerinfo",
            ):
                try:
                    rpc.load_wallet(wallet)
                except Exception:
                    pass
                result = rpc.call(method, params, wallet=wallet, retries=1)
            else:
                result = rpc.call(method, params, retries=1)
            self.console_out.appendPlainText(json.dumps(result, indent=2, default=str))
        except Exception as exc:
            self.console_out.appendPlainText(f"ERROR: {exc}")
        self.console_in.clear()

    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            dlg.apply()
            self._timer.setInterval(store.refresh_ms())
            self.refresh_all()

    def show_about(self):
        coins = list_coins(
            conf_overrides=self.conf_overrides(),
            rpc_overrides=self.rpc_overrides(),
        )
        names = ", ".join(c["ticker"] for c in coins)
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> v{__version__}<br><br>"
            "Desktop multi-fork wallet for Bloodstone mainnet (STONE) and every "
            "live Fork Lab child coin. Coins are discovered from the Fork Lab "
            "database so new launches appear automatically.<br><br>"
            f"<b>Catalogue now:</b> {names}<br><br>"
            "Connects to local JSON-RPC nodes (bloodstoned / azured / lrgkd / …).<br>"
            "https://bloodstone.rocks/",
        )

    def _init_daemon_runtime(self):
        """Locate bundled daemons next to the app / portable tree."""
        import sys as _sys
        from pathlib import Path

        from ..daemon_manager import find_bundled_daemons_root

        starts = []
        if getattr(_sys, "frozen", False):
            starts.append(Path(_sys.executable).resolve().parent)
        # .../app/bloodstone_mfq/ui/mainwindow.py → install root is parents[3]
        try:
            here = Path(__file__).resolve()
            starts.extend(list(here.parents)[:6])
        except Exception:
            pass
        starts.append(Path.cwd())
        try:
            starts.append(Path(_sys.argv[0]).resolve().parent)
        except Exception:
            pass

        root = find_bundled_daemons_root(start_paths=starts)
        if root:
            self._mgr.set_bundled_root(str(root))
            self._status.showMessage(f"Bundled daemons root: {root}", 5000)
        else:
            self._status.showMessage(
                "No bundled daemons folder found — will download on Start", 5000
            )
        self._update_daemon_status()
        # Prefetch manifest
        try:
            self._mgr.fetch_manifest(force=True)
        except Exception:
            pass

    def _toggle_auto_daemon(self):
        on = self.chk_auto_daemon.isChecked()
        self.chk_auto_daemon.setText(
            "Auto-start on select: ON" if on else "Auto-start on select: OFF"
        )

    def _update_daemon_status(self):
        t = self._current_ticker or ""
        if not t:
            self.daemon_status.setText("Daemon: —")
            return
        st = self._mgr.status(t)
        bits = [
            f"{t}",
            "installed" if st.get("installed") else "not installed",
            f"running pid={st.get('pid')}" if st.get("running") else "stopped",
        ]
        if st.get("daemon_path"):
            bits.append(str(st["daemon_path"]))
        pack = st.get("pack") or {}
        # Prefer actual RPC override port (may differ from pack default after
        # Hyper-V port fallback).
        try:
            from .. import settings_store as store

            ov = (store.rpc_overrides() or {}).get(t) or {}
            port = ov.get("rpc_port") or pack.get("rpc_port")
        except Exception:
            port = pack.get("rpc_port")
        if port:
            bits.append(f"rpc :{port}")
        if t != "STONE" and self._mgr.is_placeholder_fork_binary(t):
            bits.append("⚠ PLACEHOLDER=bloodstoned (invalid addresses)")
        self.daemon_status.setText("Daemon: " + " · ".join(bits))
        self.btn_daemon_stop.setEnabled(bool(st.get("running")))

        # Soft auto-restart: if this coin is selected, auto-start is ON, and
        # the daemon died, restart once every 45s (AZURE often dies on bad P2P
        # bind or when the GUI used to kill children on exit).
        # First try reattach (RPC may still be up on a fallback port after conf
        # drift) — never spawn a second process against a locked datadir.
        try:
            if (
                self.chk_auto_daemon.isChecked()
                and not st.get("running")
                and st.get("installed")
                and not self._daemon_busy
            ):
                reatt = self._mgr.reattach_running(t)
                if reatt and reatt.get("running") and reatt.get("rpc_port"):
                    self.daemon_status.setText(
                        f"Daemon: reattached · running · rpc :{reatt.get('rpc_port')}"
                    )
                    self.btn_daemon_stop.setEnabled(True)
                    return
                last = float(getattr(self, "_last_auto_restart", {}).get(t, 0) or 0)
                import time as _time

                if _time.time() - last > 45:
                    if not hasattr(self, "_last_auto_restart"):
                        self._last_auto_restart = {}
                    self._last_auto_restart[t] = _time.time()
                    self.daemon_progress.setText(f"{t} offline — auto-restart…")
                    QTimer.singleShot(400, self.start_local_daemon)
        except Exception:
            pass

    def start_local_daemon(self):
        t = self._current_ticker
        if not t or self._daemon_busy:
            return
        self._daemon_busy = True
        self.btn_daemon_start.setEnabled(False)
        self.daemon_progress.setText(f"Preparing {t} daemon…")

        class _Act(QThread):
            ok = pyqtSignal(dict)
            err = pyqtSignal(str)
            prog = pyqtSignal(str, int)

            def __init__(self, mgr, ticker):
                super().__init__()
                self.mgr = mgr
                self.ticker = ticker

            def run(self):
                try:
                    def p(tick, pct):
                        self.prog.emit(tick, pct)

                    result = self.mgr.activate(self.ticker, progress=p)
                    self.ok.emit(result)
                except Exception as exc:
                    self.err.emit(str(exc))

        thr = _Act(self._mgr, t)
        thr.prog.connect(
            lambda tick, pct: self.daemon_progress.setText(
                f"Downloading {tick} daemon… {pct}%"
            )
        )

        def _ok(result):
            self._daemon_busy = False
            self.btn_daemon_start.setEnabled(True)
            running = bool(result.get("running"))
            port = result.get("rpc_port")
            if running:
                self.daemon_progress.setText(
                    f"{t} running — rpc 127.0.0.1:{port}"
                )
                self._status.showMessage(
                    f"{t} daemon started (pid {result.get('pid')}) on :{port}", 8000
                )
            else:
                self.daemon_progress.setText(f"{t} started but not running")
                QMessageBox.warning(
                    self,
                    "Local daemon",
                    f"{t} process did not stay running.\n"
                    f"datadir={result.get('datadir')}\n"
                    f"Check mfq-stderr.log / debug.log in that folder.",
                )
            self._update_daemon_status()
            # RPC credentials were written — refresh balances
            QTimer.singleShot(2500, self.refresh_all)

        def _err(msg):
            self._daemon_busy = False
            self.btn_daemon_start.setEnabled(True)
            self.daemon_progress.setText(f"{t} daemon error")
            QMessageBox.warning(self, "Local daemon", msg[:1200])
            self._update_daemon_status()

        thr.ok.connect(_ok)
        thr.err.connect(_err)
        thr.start()
        self._daemon_thread = thr  # prevent GC

    def stop_local_daemon(self):
        t = self._current_ticker
        if not t:
            return
        try:
            self._mgr.stop(t)
            self.daemon_progress.setText(f"{t} daemon stopped")
        except Exception as exc:
            QMessageBox.warning(self, "Stop daemon", str(exc))
        self._update_daemon_status()

    def stop_all_daemons(self):
        try:
            self._mgr.stop_all()
            self.daemon_progress.setText("All local daemons stopped")
        except Exception as exc:
            QMessageBox.warning(self, "Stop daemons", str(exc))
        self._update_daemon_status()

    def closeEvent(self, event):
        self._timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(8000)
        # Leave local daemons running in the background so AZURE/LRGK/STONE
        # stay up when Multi-Fork Qt is closed (Windows DETACHED child).
        # Use "Stop daemon" / "Stop all" for an intentional shutdown.
        try:
            self._status.showMessage(
                "Leaving local daemons running in background…", 3000
            )
        except Exception:
            pass
        super().closeEvent(event)
