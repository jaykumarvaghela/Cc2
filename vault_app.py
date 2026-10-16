"""
Corporate Password Vault - Streamlit
Run:  pip install streamlit cryptography
      streamlit run vault_app.py

Security model
- Master password -> scrypt -> 32-byte key -> Fernet (AES-128-CBC + HMAC-SHA256)
- Only the salt + encrypted blob are written to disk. The master password and key
  live only in st.session_state (server memory) while unlocked.
- Auto-lock after inactivity, exponential back-off on failed unlocks.
"""
import base64
import csv
import io
import json
import math
import os
import secrets
import string
import time
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

VAULT_PATH = Path(os.environ.get("VAULT_PATH", Path.home() / ".corp_vault.json"))
MIN_MASTER_LEN = 12
CATEGORIES = ["General", "Cloud", "Database", "VPN / Network", "Email", "Finance", "Client", "Other"]

st.set_page_config(page_title="Corporate Vault", page_icon="🔐", layout="wide")


# ───────────────────────── crypto / storage ─────────────────────────
def derive_key(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def vault_exists() -> bool:
    return VAULT_PATH.exists()


def write_vault(key: bytes, salt: bytes, entries: list[dict]) -> None:
    token = Fernet(key).encrypt(json.dumps(entries).encode("utf-8"))
    payload = {
        "v": 1,
        "salt": base64.b64encode(salt).decode(),
        "token": token.decode(),
    }
    tmp = VAULT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(VAULT_PATH)  # atomic swap so a crash can't corrupt the vault


def read_vault(password: str):
    """Returns (key, salt, entries) or raises InvalidToken on wrong password."""
    payload = json.loads(VAULT_PATH.read_text())
    salt = base64.b64decode(payload["salt"])
    key = derive_key(password, salt)
    entries = json.loads(Fernet(key).decrypt(payload["token"].encode()).decode())
    return key, salt, entries


def persist() -> None:
    write_vault(st.session_state.key, st.session_state.salt, st.session_state.entries)


# ───────────────────────── helpers ─────────────────────────
def strength(pw: str) -> tuple[int, str]:
    """Rough entropy estimate -> (0-100 score, label). Text label so it isn't colour-only."""
    if not pw:
        return 0, "Empty"
    pool = 0
    pool += 26 if any(c.islower() for c in pw) else 0
    pool += 26 if any(c.isupper() for c in pw) else 0
    pool += 10 if any(c.isdigit() for c in pw) else 0
    pool += 32 if any(c in string.punctuation for c in pw) else 0
    bits = len(pw) * math.log2(max(pool, 2))
    if len(set(pw)) < len(pw) / 2:
        bits *= 0.7
    score = min(100, int(bits / 100 * 100))
    label = "Weak" if bits < 40 else "Fair" if bits < 60 else "Strong" if bits < 80 else "Very strong"
    return score, label


def generate_password(length, upper, digits, symbols) -> str:
    pools = [string.ascii_lowercase]
    if upper:
        pools.append(string.ascii_uppercase)
    if digits:
        pools.append(string.digits)
    if symbols:
        pools.append("!@#$%^&*()-_=+[]{};:,.?")
    alphabet = "".join(pools)
    while True:  # guarantee at least one char from every selected pool
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if all(any(c in p for c in pw) for p in pools):
            return pw


def lock() -> None:
    for k in ("key", "salt", "entries", "last_activity"):
        st.session_state.pop(k, None)


def is_unlocked() -> bool:
    return "key" in st.session_state


def fill_generated() -> None:
    st.session_state.new_pw = generate_password(
        st.session_state.gen_len, st.session_state.gen_up,
        st.session_state.gen_dig, st.session_state.gen_sym,
    )


# ───────────────────────── lock screen ─────────────────────────
def lock_screen() -> None:
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.title("🔐 Corporate Vault")
        fails = st.session_state.get("fails", 0)
        wait_until = st.session_state.get("wait_until", 0.0)

        if not vault_exists():
            st.subheader("Create your master password")
            st.caption(
                f"Minimum {MIN_MASTER_LEN} characters. A passphrase of 4+ random words works well. "
                "**There is no recovery** if you forget it."
            )
            with st.form("create"):
                p1 = st.text_input("Master password", type="password")
                p2 = st.text_input("Confirm master password", type="password")
                go = st.form_submit_button("Create vault", type="primary", use_container_width=True)
            if p1:
                score, label = strength(p1)
                st.progress(score / 100, text=f"Strength: {label}")
            if go:
                if len(p1) < MIN_MASTER_LEN:
                    st.error(f"Master password must be at least {MIN_MASTER_LEN} characters.")
                elif p1 != p2:
                    st.error("Passwords do not match.")
                else:
                    salt = os.urandom(16)
                    key = derive_key(p1, salt)
                    write_vault(key, salt, [])
                    st.session_state.update(key=key, salt=salt, entries=[], last_activity=time.time())
                    st.rerun()
            return

        st.subheader("Unlock")
        remaining = wait_until - time.time()
        if remaining > 0:
            st.warning(f"Too many failed attempts. Try again in {int(remaining) + 1}s.")
            time.sleep(1)
            st.rerun()

        with st.form("unlock"):
            pw = st.text_input("Master password", type="password")
            go = st.form_submit_button("Unlock", type="primary", use_container_width=True)
        if go:
            try:
                key, salt, entries = read_vault(pw)
            except InvalidToken:
                fails += 1
                st.session_state.fails = fails
                st.session_state.wait_until = time.time() + min(2 ** fails, 300)
                st.error("Incorrect master password.")
            except Exception as e:  # corrupt / unreadable file
                st.error(f"Could not read vault file: {e}")
            else:
                st.session_state.update(key=key, salt=salt, entries=entries, last_activity=time.time(), fails=0)
                st.rerun()


# ───────────────────────── main app ─────────────────────────
def vault_tab() -> None:
    entries = st.session_state.entries
    c1, c2 = st.columns([3, 1])
    q = c1.text_input("Search", placeholder="Title, username, URL, notes…")
    cat = c2.selectbox("Category", ["All"] + CATEGORIES)

    shown = [
        e for e in entries
        if (cat == "All" or e["category"] == cat)
        and (not q or q.lower() in " ".join([e["title"], e["username"], e["url"], e["notes"]]).lower())
    ]
    shown.sort(key=lambda e: e["title"].lower())
    st.caption(f"{len(shown)} of {len(entries)} entries")

    if not entries:
        st.info("Your vault is empty. Add your first entry in the **Add entry** tab.")

    for e in shown:
        with st.expander(f"{e['title']}  ·  {e['username']}  ·  {e['category']}"):
            if st.checkbox("Show password", key=f"show_{e['id']}"):
                st.code(e["password"], language=None)  # code block has a built-in copy button
            else:
                st.text("Password: hidden")
                st.code(e["username"], language=None)
            if e["url"]:
                st.markdown(f"**URL:** {e['url']}")
            if e["notes"]:
                st.markdown(f"**Notes:** {e['notes']}")
            st.caption(f"Last updated {e['updated']}")

            with st.form(f"edit_{e['id']}"):
                t = st.text_input("Title", e["title"])
                u = st.text_input("Username", e["username"])
                p = st.text_input("Password", e["password"], type="password")
                url = st.text_input("URL", e["url"])
                c = st.selectbox("Category", CATEGORIES, index=CATEGORIES.index(e["category"]) if e["category"] in CATEGORIES else 0)
                n = st.text_area("Notes", e["notes"])
                b1, b2 = st.columns(2)
                save = b1.form_submit_button("Save changes", type="primary", use_container_width=True)
                delete = b2.form_submit_button("Delete entry", use_container_width=True)
            if save:
                if not t.strip() or not p:
                    st.error("Title and password are required.")
                else:
                    e.update(title=t.strip(), username=u.strip(), password=p, url=url.strip(),
                             category=c, notes=n, updated=datetime.now().strftime("%Y-%m-%d %H:%M"))
                    persist()
                    st.success("Saved.")
                    st.rerun()
            if delete:
                st.session_state.entries = [x for x in entries if x["id"] != e["id"]]
                persist()
                st.rerun()


def add_tab() -> None:
    st.subheader("Add entry")
    with st.expander("Password generator", expanded=False):
        g1, g2, g3, g4 = st.columns([2, 1, 1, 1])
        g1.slider("Length", 12, 64, 20, key="gen_len")
        g2.checkbox("A-Z", True, key="gen_up")
        g3.checkbox("0-9", True, key="gen_dig")
        g4.checkbox("Symbols", True, key="gen_sym")
        st.button("Generate into password field", on_click=fill_generated)

    with st.form("add", clear_on_submit=True):
        t = st.text_input("Title *", placeholder="e.g. AWS prod console")
        u = st.text_input("Username / email")
        p = st.text_input("Password *", type="password", key="new_pw")
        url = st.text_input("URL")
        c = st.selectbox("Category", CATEGORIES)
        n = st.text_area("Notes")
        go = st.form_submit_button("Add to vault", type="primary")
    if go:
        if not t.strip() or not p:
            st.error("Title and password are required.")
        else:
            st.session_state.entries.append(dict(
                id=uuid.uuid4().hex, title=t.strip(), username=u.strip(), password=p, url=url.strip(),
                category=c, notes=n, updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
            ))
            persist()
            st.success(f"Added “{t.strip()}”.")
            st.rerun()
    if st.session_state.get("new_pw"):
        score, label = strength(st.session_state.new_pw)
        st.progress(score / 100, text=f"Password strength: {label}")


def settings_tab() -> None:
    st.subheader("Change master password")
    with st.form("change_master"):
        cur = st.text_input("Current master password", type="password")
        n1 = st.text_input("New master password", type="password")
        n2 = st.text_input("Confirm new master password", type="password")
        go = st.form_submit_button("Change master password")
    if go:
        try:
            read_vault(cur)
        except InvalidToken:
            st.error("Current master password is incorrect.")
        else:
            if len(n1) < MIN_MASTER_LEN:
                st.error(f"New password must be at least {MIN_MASTER_LEN} characters.")
            elif n1 != n2:
                st.error("New passwords do not match.")
            else:
                salt = os.urandom(16)
                key = derive_key(n1, salt)
                st.session_state.update(key=key, salt=salt)
                persist()
                st.success("Master password changed and vault re-encrypted.")

    st.subheader("Backup")
    st.download_button(
        "Download encrypted backup", VAULT_PATH.read_bytes(),
        file_name=f"vault-backup-{datetime.now():%Y%m%d}.json", mime="application/json",
    )
    st.caption("The backup is still encrypted with your master password. Store it somewhere safe.")

    st.subheader("Export plaintext CSV")
    st.warning("The CSV is **unencrypted**. Delete it as soon as you've used it.")
    if st.checkbox("I understand, prepare the CSV"):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["title", "username", "password", "url", "category", "notes", "updated"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(st.session_state.entries)
        st.download_button("Download CSV", buf.getvalue(), file_name="vault_export.csv", mime="text/csv")

    st.subheader("Import CSV")
    st.caption("Columns: title, username, password, url, category, notes (header row required).")
    up = st.file_uploader("CSV file", type="csv")
    if up and st.button("Import entries"):
        rows = csv.DictReader(io.StringIO(up.getvalue().decode("utf-8-sig")))
        count = 0
        for r in rows:
            if r.get("title") and r.get("password"):
                st.session_state.entries.append(dict(
                    id=uuid.uuid4().hex, title=r["title"], username=r.get("username", ""),
                    password=r["password"], url=r.get("url", ""),
                    category=r.get("category") if r.get("category") in CATEGORIES else "General",
                    notes=r.get("notes", ""), updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                ))
                count += 1
        persist()
        st.success(f"Imported {count} entries.")
        st.rerun()


def main() -> None:
    if is_unlocked():
        # auto-lock check (runs on every interaction)
        limit = st.session_state.get("auto_lock_min", 5) * 60
        if time.time() - st.session_state.last_activity > limit:
            lock()
            st.session_state.lock_msg = "Vault auto-locked after inactivity."
        else:
            st.session_state.last_activity = time.time()

    if not is_unlocked():
        if msg := st.session_state.pop("lock_msg", None):
            st.info(msg)
        lock_screen()
        return

    with st.sidebar:
        st.title("🔐 Vault")
        st.caption(f"{len(st.session_state.entries)} entries")
        st.selectbox("Auto-lock after (min)", [1, 5, 10, 15, 30], index=1, key="auto_lock_min")
        if st.button("🔒 Lock now", type="primary", use_container_width=True):
            lock()
            st.rerun()

    tab1, tab2, tab3 = st.tabs(["Vault", "Add entry", "Settings"])
    with tab1:
        vault_tab()
    with tab2:
        add_tab()
    with tab3:
        settings_tab()


main()
