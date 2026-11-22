
/**
 * Paraguay News - FastAPI Client
 *
 * Connects the Next.js frontend to the Python FastAPI backend.
 */

const API_URL =
  process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

// ========================================
// Types
// ========================================

export interface EventCard {
  id: number;
  title: string;
  image_url: string | null;
  article_count: number;
  source_count: number;
  latest_article_at: string;
}

export interface NewsArticle {
  id: number;
  title: string;
  url: string;
  published_at: string | null;
  source_name: string;
  source_domain: string;
}

export interface EventDetail extends EventCard {
  summary: string;
  articles: NewsArticle[];
}

// ========================================
// Homepage: Get approved events
// ========================================

export async function getEvents(
  limit: number = 30,
  offset: number = 0
): Promise<EventCard[]> {
  const response = await fetch(
    `${API_URL}/api/events?limit=${limit}&offset=${offset}`,
    {
      cache: "no-store",
    }
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch events: ${response.status} ${response.statusText}`
    );
  }

  return (await response.json()) as EventCard[];
}

// ========================================
// Event page: Get event details
// ========================================

export async function getEvent(
  eventId: number
): Promise<EventDetail> {
  const response = await fetch(
    `${API_URL}/api/events/${eventId}`,
    {
      cache: "no-store",
    }
  );

  if (response.status === 404) {
    throw new Error(`Event ${eventId} not found (404)`);
  }

  if (!response.ok) {
    throw new Error(
      `Failed to fetch event ${eventId}: ${response.status}`
    );
  }

  return (await response.json()) as EventDetail;
}

// ========================================
// Health check
// ========================================

export async function checkApiHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/api/health`, {
      cache: "no-store",
    });

    return response.ok;
  } catch {
    return false;
  }
}
