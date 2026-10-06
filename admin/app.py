from __future__ import annotations

import sys
from pathlib import Path

# Add project root to Python path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from database.db import SessionLocal

from admin.actions import (
    approve_event,
    reject_event,
    save_edits,
)

from admin.queries import (
    get_all_event_articles,
    get_context_articles,
    get_draft_events,
    get_event_for_review,
)


from admin.actions import (
    approve_event,
    reject_event,
    save_edits,
)

from admin.queries import (
    get_all_event_articles,
    get_context_articles,
    get_draft_events,
    get_event_for_review,
)


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="Paraguay News — Review",
    page_icon="📰",
    layout="wide",
)


# =========================================================
# HELPERS
# =========================================================

def effective_time(row):
    return (
        row.published_at
        or row.scraped_at
    )


def format_datetime(value):

    if value is None:
        return "Sin fecha"

    return value.strftime(
        "%Y-%m-%d %H:%M"
    )


def render_article(
    article,
    context=False,
):
    """
    Render one article as an expandable card.
    """

    source = (
        article.source_name
    )

    title = (
        article.title
        or "Sin título"
    )

    timestamp = effective_time(
        article
    )

    prefix = ""

    if (
        context
        and article.is_representative
    ):
        prefix = "⭐ "

    expander_title = (
        f"{prefix}{source} — {title}"
    )

    with st.expander(
        expander_title
    ):

        left, right = st.columns(
            [3, 1]
        )

        with left:

            st.caption(
                format_datetime(
                    timestamp
                )
            )

            if context:

                st.caption(
                    f"Context position: "
                    f"{article.position}"
                )

                if article.is_representative:

                    st.markdown(
                        "**Representative article**"
                    )

        with right:

            if article.url:

                st.link_button(
                    "Open original ↗",
                    article.url,
                    use_container_width=True,
                )

        st.markdown(
            "#### Article text"
        )

        if article.body:

            st.write(
                article.body
            )

        else:

            st.info(
                "No article body available."
            )


# =========================================================
# SIDEBAR
# =========================================================

session = SessionLocal()

try:

    drafts = get_draft_events(
        session
    )

    st.sidebar.title(
        "Editorial Review"
    )

    st.sidebar.metric(
        "Drafts",
        len(drafts),
    )

    if not drafts:

        st.success(
            "There are no drafts waiting "
            "for review."
        )

        st.stop()

    event_options = {
        (
            f"{row.id} · "
            f"{row.article_count} articles · "
            f"{row.generated_title}"
        ):
            row.id

        for row in drafts
    }

    selected_label = (
        st.sidebar.selectbox(
            "Select event",
            list(
                event_options.keys()
            ),
        )
    )

    event_id = event_options[
        selected_label
    ]

    event = get_event_for_review(
        session,
        event_id,
    )

    if event is None:

        st.error(
            "Event not found."
        )

        st.stop()

    context_articles = (
        get_context_articles(
            session,
            event_id,
        )
    )

    all_articles = (
        get_all_event_articles(
            session,
            event_id,
        )
    )


    # =====================================================
    # HEADER
    # =====================================================

    st.title(
        "Event Review"
    )

    header_left, header_middle, header_right = (
        st.columns(
            [2, 1, 1]
        )
    )

    with header_left:

        st.markdown(
            f"### Event {event.id}"
        )

        st.caption(
            f"Original seed title: "
            f"{event.original_title}"
        )

    with header_middle:

        st.metric(
            "Articles",
            event.article_count,
        )

    with header_right:

        source_count = len(
            {
                article.source_id
                for article
                in all_articles
            }
        )

        st.metric(
            "Sources",
            source_count,
        )


    # =====================================================
    # GENERATED CONTENT
    # =====================================================

    st.divider()

    st.subheader(
        "Generated content"
    )

    st.caption(
        f"Model: {event.model} · "
        f"Generated: "
        f"{format_datetime(event.generated_at)}"
    )

    st.info(
        "This is an AI-generated draft. "
        "Review the source coverage below "
        "before approving it."
    )

    # If human edits already exist, show those.
    # Otherwise initialize from generated content.

    initial_title = (
        event.final_title
        if event.final_title
        else event.generated_title
    )

    initial_summary = (
        event.final_summary
        if event.final_summary
        else event.generated_summary
    )

    title = st.text_input(
        "Title",
        value=initial_title,
        key=f"title_{event.id}",
    )

    summary = st.text_area(
        "Summary",
        value=initial_summary,
        height=180,
        key=f"summary_{event.id}",
    )


    # =====================================================
    # ACTIONS
    # =====================================================

    save_col, approve_col, reject_col = (
        st.columns(
            [1, 1, 1]
        )
    )

    with save_col:

        if st.button(
            "💾 Save edits",
            use_container_width=True,
        ):

            save_edits(
                session,
                event.id,
                title,
                summary,
            )

            st.success(
                "Edits saved."
            )

            st.rerun()

    with approve_col:

        if st.button(
            "✅ Approve",
            type="primary",
            use_container_width=True,
        ):

            approve_event(
                session,
                event.id,
                title,
                summary,
            )

            st.success(
                "Event approved."
            )

            st.rerun()

    with reject_col:

        if st.button(
            "❌ Reject",
            use_container_width=True,
        ):

            reject_event(
                session,
                event.id,
            )

            st.warning(
                "Event rejected."
            )

            st.rerun()


    # =====================================================
    # ORIGINAL AI OUTPUT
    # =====================================================

    with st.expander(
        "View original AI generation"
    ):

        st.markdown(
            "**Generated title**"
        )

        st.write(
            event.generated_title
        )

        st.markdown(
            "**Generated summary**"
        )

        st.write(
            event.generated_summary
        )


    # =====================================================
    # QWEN CONTEXT
    # =====================================================

    st.divider()

    st.subheader(
        "Context used by Qwen"
    )

    st.caption(
        f"{len(context_articles)} of "
        f"{len(all_articles)} event articles "
        f"were provided to the model."
    )

    if not context_articles:

        st.warning(
            "No stored LLM context exists for "
            "this draft. This is probably one "
            "of the drafts generated before "
            "context persistence was added."
        )

    else:

        context_sources = len(
            {
                article.source_id
                for article
                in context_articles
            }
        )

        st.caption(
            f"{context_sources} different sources "
            f"in the model context."
        )

        for article in context_articles:

            render_article(
                article,
                context=True,
            )


    # =====================================================
    # ALL EVENT COVERAGE
    # =====================================================

    st.divider()

    st.subheader(
        "All event coverage"
    )

    st.caption(
        f"{len(all_articles)} articles from "
        f"{source_count} sources."
    )


    # -----------------------------------------------------
    # Filters
    # -----------------------------------------------------

    sources = sorted(
        {
            article.source_name
            for article
            in all_articles
        }
    )

    filter_col, search_col = (
        st.columns(
            [1, 2]
        )
    )

    with filter_col:

        selected_source = (
            st.selectbox(
                "Source",
                ["All"] + sources,
                key=f"source_{event.id}",
            )
        )

    with search_col:

        search = (
            st.text_input(
                "Search titles",
                key=f"search_{event.id}",
                placeholder=(
                    "Search article titles..."
                ),
            )
            .strip()
            .lower()
        )


    # -----------------------------------------------------
    # Apply filters
    # -----------------------------------------------------

    filtered_articles = []

    for article in all_articles:

        if (
            selected_source != "All"
            and article.source_name
            != selected_source
        ):
            continue

        if (
            search
            and search
            not in (
                article.title
                or ""
            ).lower()
        ):
            continue

        filtered_articles.append(
            article
        )


    # -----------------------------------------------------
    # Context IDs so we can identify articles already
    # shown to Qwen.
    # -----------------------------------------------------

    context_ids = {
        article.article_id
        for article
        in context_articles
    }


    st.caption(
        f"Showing "
        f"{len(filtered_articles)} articles."
    )


    # -----------------------------------------------------
    # Render all event articles
    # -----------------------------------------------------

    for article in filtered_articles:

        badges = []

        if (
            article.article_id
            == event.representative_article_id
        ):

            badges.append(
                "⭐ Representative"
            )

        if (
            article.article_id
            in context_ids
        ):

            badges.append(
                "🤖 Qwen context"
            )

        if article.is_seed:

            badges.append(
                "🌱 Event seed"
            )

        if badges:

            st.caption(
                " · ".join(
                    badges
                )
            )

        render_article(
            article,
            context=False,
        )

finally:

    session.close()
