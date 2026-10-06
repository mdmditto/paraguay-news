from __future__ import annotations

import sys
from pathlib import Path

# =========================================================
# PROJECT PATH
# =========================================================

# Add project root to Python path so imports such as
# "database" and "admin" work correctly with Streamlit.

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# =========================================================
# IMPORTS
# =========================================================

import streamlit as st

from database.db import SessionLocal

from admin.actions import (
    approve_event,
    reject_event,
    save_edits,
    select_event_image,
)

from admin.queries import (
    get_all_event_articles,
    get_context_articles,
    get_draft_events,
    get_event_for_review,
)


# =========================================================
# PAGE CONFIGURATION
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
    """
    Use published_at when available.
    Otherwise fall back to scraped_at.
    """

    return (
        row.published_at
        or row.scraped_at
    )


def format_datetime(value):
    """
    Format datetime for display.
    """

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
    Render one article inside an expandable card.
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


def render_image_candidate(
    article,
    event,
    session,
    button_key_prefix,
):
    """
    Render an image candidate and allow the user
    to select it as the event image.
    """

    if not article.image_url:
        return

    # -----------------------------------------------------
    # Image
    # -----------------------------------------------------

    try:

        st.image(
            article.image_url,
            use_container_width=True,
        )

    except Exception:

        st.warning(
            "Could not load image."
        )

    # -----------------------------------------------------
    # Source
    # -----------------------------------------------------

    st.markdown(
        f"**{article.source_name}**"
    )

    # -----------------------------------------------------
    # Article title
    # -----------------------------------------------------

    if article.title:

        st.caption(
            article.title
        )

    # -----------------------------------------------------
    # Badges
    # -----------------------------------------------------

    if (
        article.article_id
        == event.representative_article_id
    ):

        st.caption(
            "⭐ Representative article"
        )

    # -----------------------------------------------------
    # Original article
    # -----------------------------------------------------

    if article.url:

        st.link_button(
            "Open article ↗",
            article.url,
            use_container_width=True,
        )

    # -----------------------------------------------------
    # Selected / Select button
    # -----------------------------------------------------

    if (
        article.article_id
        == event.selected_image_article_id
    ):

        st.success(
            "✓ Selected image"
        )

    else:

        if st.button(
            "Select image",
            key=(
                f"{button_key_prefix}_"
                f"{event.id}_"
                f"{article.article_id}"
            ),
            use_container_width=True,
        ):

            select_event_image(
                session,
                event.id,
                article.article_id,
            )

            st.rerun()


# =========================================================
# DATABASE SESSION
# =========================================================

session = SessionLocal()

try:

    # =====================================================
    # LOAD DRAFTS
    # =====================================================

    drafts = get_draft_events(
        session
    )


    # =====================================================
    # SIDEBAR
    # =====================================================

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


    # -----------------------------------------------------
    # Event selector
    # -----------------------------------------------------

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


    # =====================================================
    # LOAD EVENT
    # =====================================================

    event = get_event_for_review(
        session,
        event_id,
    )

    if event is None:

        st.error(
            "Event not found."
        )

        st.stop()


    # =====================================================
    # LOAD CONTEXT ARTICLES
    # =====================================================

    context_articles = (
        get_context_articles(
            session,
            event_id,
        )
    )


    # =====================================================
    # LOAD ALL EVENT ARTICLES
    # =====================================================

    all_articles = (
        get_all_event_articles(
            session,
            event_id,
        )
    )


    # =====================================================
    # EVENT STATISTICS
    # =====================================================

    source_count = len(
        {
            article.source_id
            for article
            in all_articles
        }
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


    # -----------------------------------------------------
    # Existing human edits take priority.
    # Otherwise initialize editor with AI generation.
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # Editable title
    # -----------------------------------------------------

    title = st.text_input(
        "Title",
        value=initial_title,
        key=f"title_{event.id}",
    )


    # -----------------------------------------------------
    # Editable summary
    # -----------------------------------------------------

    summary = st.text_area(
        "Summary",
        value=initial_summary,
        height=180,
        key=f"summary_{event.id}",
    )


    # =====================================================
    # ACTION BUTTONS
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

            try:

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

            except ValueError as exc:

                st.error(
                    str(exc)
                )


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
    # EVENT IMAGE
    # =====================================================

    st.divider()

    st.subheader(
        "Event image"
    )

    st.caption(
        "Select the image that should represent "
        "this event on the website."
    )


    # -----------------------------------------------------
    # Find selected image article
    # -----------------------------------------------------

    selected_image_article = None

    if event.selected_image_article_id:

        for article in all_articles:

            if (
                article.article_id
                == event.selected_image_article_id
            ):

                selected_image_article = article
                break


    # -----------------------------------------------------
    # Display currently selected image
    # -----------------------------------------------------

    if selected_image_article:

        st.markdown(
            "### Selected image"
        )

        selected_left, selected_right = (
            st.columns(
                [2, 1]
            )
        )

        with selected_left:

            try:

                st.image(
                    selected_image_article.image_url,
                    use_container_width=True,
                )

            except Exception:

                st.warning(
                    "Could not load selected image."
                )

        with selected_right:

            st.markdown(
                f"**{selected_image_article.source_name}**"
            )

            st.write(
                selected_image_article.title
            )

            st.caption(
                f"Article ID: "
                f"{selected_image_article.article_id}"
            )

            if selected_image_article.url:

                st.link_button(
                    "Open original article ↗",
                    selected_image_article.url,
                    use_container_width=True,
                )

    else:

        st.info(
            "No event image selected yet."
        )


    # =====================================================
    # CONTEXT IMAGE CANDIDATES
    # =====================================================

    st.markdown(
        "### Image candidates"
    )

    st.caption(
        "Images from articles used in the "
        "Qwen context are shown first."
    )


    context_image_articles = [
        article
        for article in context_articles
        if article.image_url
    ]


    if not context_image_articles:

        st.warning(
            "None of the context articles "
            "contains an image."
        )

    else:

        st.caption(
            f"{len(context_image_articles)} "
            f"context articles have images."
        )

        # Three images per row.

        for start in range(
            0,
            len(context_image_articles),
            3,
        ):

            batch = (
                context_image_articles[
                    start:start + 3
                ]
            )

            columns = st.columns(3)

            for column, article in zip(
                columns,
                batch,
            ):

                with column:

                    render_image_candidate(
                        article=article,
                        event=event,
                        session=session,
                        button_key_prefix=(
                            "context_image"
                        ),
                    )


    # =====================================================
    # ALL EVENT IMAGE CANDIDATES
    # =====================================================

    with st.expander(
        "Show images from all event articles"
    ):

        all_image_articles = [
            article
            for article in all_articles
            if article.image_url
        ]

        st.caption(
            f"{len(all_image_articles)} of "
            f"{len(all_articles)} articles "
            f"have an image."
        )


        if not all_image_articles:

            st.info(
                "No images are available "
                "for this event."
            )

        else:

            # Three images per row.

            for start in range(
                0,
                len(all_image_articles),
                3,
            ):

                batch = (
                    all_image_articles[
                        start:start + 3
                    ]
                )

                columns = st.columns(3)

                for column, article in zip(
                    columns,
                    batch,
                ):

                    with column:

                        render_image_candidate(
                            article=article,
                            event=event,
                            session=session,
                            button_key_prefix=(
                                "all_image"
                            ),
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


        # -------------------------------------------------
        # Display context articles
        # -------------------------------------------------

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


    # =====================================================
    # COVERAGE FILTERS
    # =====================================================

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


    # -----------------------------------------------------
    # Source filter
    # -----------------------------------------------------

    with filter_col:

        selected_source = (
            st.selectbox(
                "Source",
                ["All"] + sources,
                key=f"source_{event.id}",
            )
        )


    # -----------------------------------------------------
    # Search titles
    # -----------------------------------------------------

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


    # =====================================================
    # APPLY FILTERS
    # =====================================================

    filtered_articles = []

    for article in all_articles:

        # -------------------------------------------------
        # Source
        # -------------------------------------------------

        if (
            selected_source != "All"
            and article.source_name
            != selected_source
        ):

            continue


        # -------------------------------------------------
        # Search
        # -------------------------------------------------

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


    # =====================================================
    # CONTEXT IDS
    # =====================================================

    context_ids = {
        article.article_id
        for article
        in context_articles
    }


    # =====================================================
    # COVERAGE COUNT
    # =====================================================

    st.caption(
        f"Showing "
        f"{len(filtered_articles)} articles."
    )


    # =====================================================
    # RENDER ALL ARTICLES
    # =====================================================

    for article in filtered_articles:

        badges = []


        # -------------------------------------------------
        # Representative
        # -------------------------------------------------

        if (
            article.article_id
            == event.representative_article_id
        ):

            badges.append(
                "⭐ Representative"
            )


        # -------------------------------------------------
        # Qwen context
        # -------------------------------------------------

        if (
            article.article_id
            in context_ids
        ):

            badges.append(
                "🤖 Qwen context"
            )


        # -------------------------------------------------
        # Event seed
        # -------------------------------------------------

        if article.is_seed:

            badges.append(
                "🌱 Event seed"
            )


        # -------------------------------------------------
        # Selected event image
        # -------------------------------------------------

        if (
            article.article_id
            == event.selected_image_article_id
        ):

            badges.append(
                "🖼️ Event image"
            )


        # -------------------------------------------------
        # Display badges
        # -------------------------------------------------

        if badges:

            st.caption(
                " · ".join(
                    badges
                )
            )


        # -------------------------------------------------
        # Article
        # -------------------------------------------------

        render_article(
            article,
            context=False,
        )


# =========================================================
# CLOSE DATABASE SESSION
# =========================================================

finally:

    session.close()