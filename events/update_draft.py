"""Manual update proposals; current event_content is never changed until apply.
Run: python -m events.update_draft generate --event-id 4151 --dry-run
     python -m events.update_draft generate --event-id 4151
     python -m events.update_draft show --event-id 4151
     python -m events.update_draft apply --proposal-id 123
     python -m events.update_draft discard --proposal-id 123
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from sqlalchemy import text, select, delete
from database.db import SessionLocal
from database.models import Event, EventContent, EventContentContext
from events.build_event_context import load_event_articles, select_context_articles, build_context
from events.generate_event_content import MAX_CONTEXT_ARTICLES, OLLAMA_MODEL, build_llm_prompt, call_ollama


def generate(session, args):
    event = session.get(Event, args.event_id)
    current = session.get(EventContent, args.event_id)
    if event is None or current is None:
        raise ValueError('Event and an existing draft/approved content are required')
    if event.representative_article_id is None:
        raise ValueError('Event has no representative article')
    pending = session.execute(text("SELECT id FROM event_update_proposals WHERE event_id=:id AND status='pending'"), {'id': args.event_id}).scalar_one_or_none()
    if pending:
        raise ValueError(f'Pending proposal {pending} already exists. Apply or discard it first.')
    articles = load_event_articles(session, event.id)
    selected = select_context_articles(articles, event.representative_article_id, max_articles=args.max_context_articles)
    if not selected:
        raise ValueError('No context articles available')
    context = build_context(event, articles, selected)
    ids = [int(a['article_id']) for a in context['articles']]
    print(f'Event {event.id}: {event.article_count} articles, context IDs={ids}')
    print(f'Current status={current.status}; current title={current.final_title or current.generated_title}')
    if args.dry_run:
        print('DRY RUN: no model call or writes')
        return
    result = call_ollama(build_llm_prompt(context))
    # Do not keep a read transaction open across the slow model call.
    session.rollback()
    # Lock parent event, then ensure the proposal slot is still available.
    session.execute(text('SELECT id FROM events WHERE id=:id FOR UPDATE'), {'id': args.event_id})
    if session.execute(text("SELECT id FROM event_update_proposals WHERE event_id=:id AND status='pending'"), {'id': args.event_id}).scalar_one_or_none():
        raise ValueError('Another pending proposal appeared during generation')
    session.execute(text('''INSERT INTO event_update_proposals
        (event_id, generated_title, generated_summary, model, article_count_at_generation, context_article_ids)
        VALUES (:event_id, :title, :summary, :model, :count, CAST(:ids AS jsonb))'''),
        {'event_id': args.event_id, 'title': result['title'], 'summary': result['summary'],
         'model': OLLAMA_MODEL, 'count': context['article_count'], 'ids': __import__('json').dumps(ids)})
    session.commit()
    print('Proposal saved for review. Current content is unchanged.')
    print('Proposed title:', result['title'])
    print('Proposed summary:', result['summary'])


def show(session, args):
    rows = session.execute(text('''SELECT id, status, generated_title, generated_summary,
        edited_title, edited_summary, article_count_at_generation, context_article_ids, generated_at
        FROM event_update_proposals WHERE event_id=:id ORDER BY id DESC LIMIT 10'''), {'id': args.event_id}).mappings().all()
    for r in rows:
        print('\n' + '='*60)
        for k,v in r.items(): print(f'{k}: {v}')


def resolve(session, args, apply):
    # Lock event first, consistent with the trigger's parent-event lock order.
    event_id = session.execute(text('SELECT event_id FROM event_update_proposals WHERE id=:id'), {'id': args.proposal_id}).scalar_one_or_none()
    if event_id is None: raise ValueError('Proposal not found')
    session.execute(text('SELECT id FROM events WHERE id=:id FOR UPDATE'), {'id': event_id})
    row = session.execute(text('SELECT * FROM event_update_proposals WHERE id=:id FOR UPDATE'), {'id': args.proposal_id}).mappings().one()
    if row['status'] != 'pending': raise ValueError('Proposal is no longer pending')
    if apply:
        content = session.get(EventContent, event_id)
        if content is None: raise ValueError('Current content missing')
        if content.status == 'approved' and not args.replace_approved:
            raise ValueError('Approved content protected. Use --replace-approved only if you accept that public approved content becomes a draft.')
        # Replace context first so the event_content UPDATE trigger captures the new context.
        session.execute(delete(EventContentContext).where(EventContentContext.event_id == event_id))
        representative_id = session.get(Event, event_id).representative_article_id
        for pos, article_id in enumerate(row['context_article_ids'], 1):
            session.add(EventContentContext(event_id=event_id, article_id=int(article_id),
                                            position=pos, is_representative=(int(article_id)==representative_id)))
        session.flush()
        # Apply to working copy, but do NOT auto-approve/publish.
        content.generated_title = row['edited_title'] or row['generated_title']
        content.generated_summary = row['edited_summary'] or row['generated_summary']
        content.final_title = None
        content.final_summary = None
        content.status = 'draft'
        content.reviewed_at = None
        content.model = row['model']
        content.generated_at = row['generated_at']
        session.flush()  # trigger snapshots new content and context atomically
    session.execute(text('''UPDATE event_update_proposals SET status=:status, resolved_at=:now
                            WHERE id=:id'''), {'status': 'applied' if apply else 'discarded',
                                               'now': datetime.now(timezone.utc), 'id': args.proposal_id})
    session.commit()
    print('Applied to editable working draft (NOT approved).' if apply else 'Proposal discarded. Current content unchanged.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command', required=True)
    g=sub.add_parser('generate');g.add_argument('--event-id',type=int,required=True);g.add_argument('--dry-run',action='store_true');g.add_argument('--max-context-articles',type=int,default=MAX_CONTEXT_ARTICLES)
    s=sub.add_parser('show');s.add_argument('--event-id',type=int,required=True)
    for cmd in ('apply','discard'):
        sp=sub.add_parser(cmd);sp.add_argument('--proposal-id',type=int,required=True)
        if cmd=='apply':sp.add_argument('--replace-approved',action='store_true')
    args=p.parse_args()
    if getattr(args,'max_context_articles',1)<1:p.error('max-context-articles must be positive')
    with SessionLocal() as session:
        try:
            if args.command=='generate':generate(session,args)
            elif args.command=='show':show(session,args)
            else:resolve(session,args,args.command=='apply')
        except Exception:
            session.rollback()
            raise
if __name__=='__main__':main()
