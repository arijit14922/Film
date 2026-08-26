"""Hall & OTT — a Streamlit cinema release tracker."""

from __future__ import annotations

import json
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


GIST_FILENAME = "hall-ott-data.json"
PLATFORMS = ["Netflix", "Amazon Prime Video", "JioHotstar", "Zee5", "SonyLIV"]

st.set_page_config(
    page_title="Hall & OTT",
    page_icon=":material/movie:",
    layout="wide",
)


def default_hall() -> pd.DataFrame:
    return pd.DataFrame([{"Name": "Movie title", "Date": date.today()}])


def default_ott() -> pd.DataFrame:
    return pd.DataFrame(
        [{"Name": "Show title", "Date": date.today(), "Platform": "Netflix"}]
    )


def rows_to_frame(rows: object, *, ott: bool) -> pd.DataFrame:
    columns = ["Name", "Date", "Platform"] if ott else ["Name", "Date"]
    clean_rows = rows if isinstance(rows, list) else []
    normalized = []
    for row in clean_rows:
        if not isinstance(row, list):
            continue
        item = {column: row[index] if index < len(row) else "" for index, column in enumerate(columns)}
        item["Date"] = pd.to_datetime(item["Date"], errors="coerce").date()
        if pd.isna(item["Date"]):
            item["Date"] = date.today()
        if ott and item["Platform"] not in PLATFORMS:
            item["Platform"] = "Netflix"
        normalized.append(item)
    return pd.DataFrame(normalized, columns=columns)


def frame_to_rows(frame: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    for record in frame.fillna("").to_dict("records"):
        values = []
        for value in record.values():
            if isinstance(value, date):
                value = value.strftime("%a, %b %d, %Y").replace(" 0", " ")
            values.append(str(value).strip())
        rows.append(values)
    return rows


def gist_request(method: str, token: str, gist_id: str, payload: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Hall-OTT-Streamlit",
    }
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = Request(
        f"https://api.github.com/gists/{gist_id}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        messages = {
            401: "GitHub rejected the token.",
            403: "The token does not have permission to edit this Gist.",
            404: "The Gist was not found. Check its ID.",
        }
        raise RuntimeError(messages.get(error.code, f"GitHub returned error {error.code}.")) from error
    except URLError as error:
        raise RuntimeError("Could not reach GitHub. Check your connection.") from error


def load_from_gist() -> None:
    token = st.session_state.gist_token.strip()
    gist_id = st.session_state.gist_id.strip()
    if not token or not gist_id:
        st.warning("Add a GitHub token and Gist ID in settings first.", icon=":material/warning:")
        return
    try:
        gist = gist_request("GET", token, gist_id)
        file = gist.get("files", {}).get(GIST_FILENAME)
        if not file:
            raise RuntimeError(f"The Gist does not contain {GIST_FILENAME}.")
        payload = json.loads(file["content"])
        st.session_state.hall = rows_to_frame(payload.get("hall"), ott=False)
        st.session_state.ott = rows_to_frame(payload.get("ott"), ott=True)
        st.session_state.editor_version += 1
        st.toast("Loaded from Gist", icon=":material/cloud_download:")
    except (RuntimeError, json.JSONDecodeError, KeyError) as error:
        st.error(str(error), icon=":material/error:")


def save_to_gist(hall: pd.DataFrame, ott: pd.DataFrame) -> None:
    token = st.session_state.gist_token.strip()
    gist_id = st.session_state.gist_id.strip()
    if not token or not gist_id:
        st.warning("Add a GitHub token and Gist ID in settings first.", icon=":material/warning:")
        return
    content = json.dumps(
        {"hall": frame_to_rows(hall), "ott": frame_to_rows(ott)}, indent=2
    )
    try:
        gist_request(
            "PATCH",
            token,
            gist_id,
            {"files": {GIST_FILENAME: {"content": content}}},
        )
        st.session_state.hall = hall.copy()
        st.session_state.ott = ott.copy()
        st.toast("Saved to Gist", icon=":material/cloud_done:")
    except RuntimeError as error:
        st.error(str(error), icon=":material/error:")


@st.dialog("Gist sync settings", icon=":material/settings:")
def settings_dialog() -> None:
    st.caption("Credentials stay in this Streamlit session and are never written to the project.")
    with st.form("gist_settings"):
        token = st.text_input(
            "GitHub personal access token",
            value=st.session_state.gist_token,
            type="password",
            placeholder="github_pat_…",
        )
        gist_id = st.text_input(
            "Gist ID",
            value=st.session_state.gist_id,
            placeholder="4b2e1f8a3c9d0e7f6a5b",
        )
        submitted = st.form_submit_button(
            "Save settings", type="primary", icon=":material/save:"
        )
    st.markdown(
        "Create a token with **Gists: read and write** access, then create a Gist "
        f"containing `{GIST_FILENAME}`."
    )
    st.link_button(
        "Open GitHub token settings",
        "https://github.com/settings/tokens",
        icon=":material/open_in_new:",
    )
    if submitted:
        if not token.strip() or not gist_id.strip():
            st.error("Both fields are required.")
        else:
            st.session_state.gist_token = token.strip()
            st.session_state.gist_id = gist_id.strip()
            st.rerun()


st.session_state.setdefault("gist_token", "")
st.session_state.setdefault("gist_id", "")
st.session_state.setdefault("hall", default_hall())
st.session_state.setdefault("ott", default_ott())
st.session_state.setdefault("editor_version", 0)

with st.container(horizontal=True, horizontal_alignment="right"):
    if st.button("Settings", icon=":material/settings:"):
        settings_dialog()
    if st.button("Load", icon=":material/cloud_download:"):
        load_from_gist()

st.title("Hall & OTT")
st.caption("Keep theatrical and streaming releases together in one simple watchlist.")

hall_column, ott_column = st.columns([0.85, 1.4], gap="large")

with hall_column:
    with st.container(border=True):
        st.header("Hall", icon=":material/theaters:")
        hall_edited = st.data_editor(
            st.session_state.hall,
            key=f"hall_editor_{st.session_state.editor_version}",
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "Name": st.column_config.TextColumn("Movie", required=True, pinned=True),
                "Date": st.column_config.DateColumn("Release date", format="ddd, MMM D, YYYY"),
            },
        )

with ott_column:
    with st.container(border=True):
        st.header("OTT", icon=":material/live_tv:")
        ott_edited = st.data_editor(
            st.session_state.ott,
            key=f"ott_editor_{st.session_state.editor_version}",
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "Name": st.column_config.TextColumn("Show", required=True, pinned=True),
                "Date": st.column_config.DateColumn("Release date", format="ddd, MMM D, YYYY"),
                "Platform": st.column_config.SelectboxColumn(
                    "Platform", options=PLATFORMS, required=True
                ),
            },
        )

with st.container(horizontal=True, horizontal_alignment="right"):
    if st.button("Save to Gist", type="primary", icon=":material/cloud_upload:"):
        save_to_gist(hall_edited, ott_edited)

if st.session_state.gist_id:
    st.caption("Gist sync is configured for this session.", icon=":material/check_circle:")
else:
    st.caption("Gist sync is optional. Open settings to connect it.", icon=":material/info:")
